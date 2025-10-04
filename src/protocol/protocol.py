import socket
from protocol.archive import ArchiveSender, ArchiveRecv
from constants import ACK_TIMEOUT, TUPLA_DIR_ENVIO, WINDOW_SIZE

def handshake(sock: socket, name: str, type: str, protocol: str, server_addr):
    """
    Realiza el handshake inicial con el servidor.
    Envía el tipo de conexión (UPLOAD o DOWNLOAD), el protocolo (SW o GBN) y el nombre del archivo.
    """
    stop_and_wait(sock, type.encode(), server_addr)
    stop_and_wait(sock, protocol.encode(), server_addr)
    stop_and_wait(sock, name.encode(), server_addr)
  
def upload_stop_and_wait(sock: socket, arch: ArchiveSender, end, server_addr):
    """
    Sube un archivo usando el protocolo Stop and Wait.
    Envía un paquete, espera ACK, y reenvía si no se recibe confirmación.
    """
    seq_num = 0
    while not end:
        pkg = arch.next_pkg(seq_num)
        if pkg is None:
            # Crear paquete END con flag_end = 1
            first_byte = (seq_num << 1) | 1  # flag_end = 1 para END
            pkg = first_byte.to_bytes(1, "big") + (0).to_bytes(2, "big")  # data_len = 0
            end = True

        stop_and_wait(sock, pkg, server_addr)
        seq_num = 1 - seq_num

def download_stop_and_wait(sock: socket, arch: ArchiveRecv, end, server_addr):
    """
    Descarga un archivo usando el protocolo Stop and Wait.
    Recibe paquetes del servidor y envía ACK de confirmación.
    """
    seq_expected = 0
    work_done = False
    print(">>> Cliente: empezando a recibir archivo...")

    while not work_done:
        try:
            print(">>> Cliente: esperando paquete del servidor...")
            sock.settimeout(5.0)
            pkg, addr = sock.recvfrom(1024)
            print(f">>> Cliente: recibí paquete de {len(pkg)} bytes")
        except socket.timeout:
            print(">>> Cliente: timeout esperando paquetes del servidor")
            break

        seq_num, flag_end, data_len, data = arch.recv_pckg(pkg)
        print(f">>> Cliente: recibí seq={seq_num}, flag_end={flag_end}, esperado={seq_expected}, len={data_len}")

        if flag_end == 1:
            print(">>> Cliente: transferencia finalizada.")
            work_done = True
            sock.sendto(seq_expected.to_bytes(4, "big"), server_addr)  # ACK de 4 bytes
            arch.archivo.close()
            break

        if seq_num == seq_expected:
            arch.archivo.write(data)
            arch.archivo.flush()
            sock.sendto((seq_num % 256).to_bytes(1, "big"), server_addr)  # ACK de 1 bit
            print(f">>> Cliente: mando ACK{seq_num}")
            seq_expected = 1 - seq_expected
        else:
            sock.sendto((1 - seq_expected).to_bytes(1, "big"), server_addr)  # ACK de 1 bit
            print(f">>> Cliente: paquete duplicado, reenvío ACK{1 - seq_expected}")

def stop_and_wait(sock: socket, msg, addr):
    """
    Envía un mensaje usando el protocolo Stop and Wait.
    Reenvía el mensaje hasta recibir confirmación ACK.
    """
    sock.sendto(msg, addr)
    ack_recv = False
    while not ack_recv:
        sock.settimeout(ACK_TIMEOUT)
        try:
            pkg, addr = sock.recvfrom(1024)
            if len(pkg) == 1:  # ACK de 1 bit
                ack_recv = True
                ack_value = int.from_bytes(pkg, "big")
                print(f"ACK recibido: {ack_value}")
            else:
                print(f"Paquete no es ACK válido: {pkg}")
        except socket.timeout:
            print("timeout, no recibi ACK")
            sock.sendto(msg, addr)

def upload_go_back_n(sock: socket, arch: ArchiveSender, end, window_sz, server_addr):
    """
    Sube un archivo usando el protocolo Go Back N.
    Utiliza una ventana deslizante para enviar múltiples paquetes sin esperar confirmación.
    """
    seq_num = 0
    pkgs_not_ack = {}
    file_finished = False

    while not end:
        # Fase 1: Enviar paquetes hasta llenar la ventana o terminar el archivo
        while(len(pkgs_not_ack) < window_sz and not file_finished):
            pkg, pkg_id = arch.next_pkg_go_back_n(seq_num)  # Usar seq_num completo
            if pkg is None:
                # Crear paquete END con flag_end = 1
                first_byte = 1  # flag_end = 1 para END
                pkg = first_byte.to_bytes(1, "big") + (0).to_bytes(2, "big") + (0).to_bytes(4, "big")  # data_len = 0, pkg_id = 0
                pkg_id = (0).to_bytes(4, "big")  # pkg_id = 0 para END
                file_finished = True
                pkgs_not_ack[pkg_id] = pkg
            sock.sendto(pkg, server_addr)
            if pkg_id != (0).to_bytes(4, "big"):
                pkgs_not_ack[pkg_id] = pkg
            seq_num += 1
        
        # Fase 2: Esperar ACKs
        print("termine de enviar los paquetes, tengo que esperar ACK")
        sock.settimeout(ACK_TIMEOUT)
        try:
            pkg, addr = sock.recvfrom(1024)
            print(f"recibi el ACK del paquete: {pkg}")
            if len(pkg) == 4:
                ack_num = int.from_bytes(pkg, "big")
                to_remove = []
                for pkg_id in pkgs_not_ack:
                    pkg_id_num = int.from_bytes(pkg_id, 'big')
                    if pkg_id_num <= ack_num:
                        to_remove.append(pkg_id)
                for pkg_id in to_remove:
                    del pkgs_not_ack[pkg_id]
                
                if file_finished and not pkgs_not_ack:
                    end = True

        except socket.timeout:
            if file_finished and not pkgs_not_ack:
                # Si terminamos el archivo y no hay paquetes sin confirmar, salir
                end = True
            else:
                print("timeout, no recibi ACKs, reenvio los n paquetes")
                for value in pkgs_not_ack.values():
                    sock.sendto(value, addr)

def download_go_back_n(sock: socket, arch: ArchiveRecv, end, server_addr, window_sz=WINDOW_SIZE):
    """
    Descarga un archivo usando el protocolo Go Back N.
    Funciona como stop and wait desde el lado del receptor.
    """
    seq_expected = 0
    work_done = False
    print(">>> Cliente: empezando a recibir archivo con Go Back N...")

    while not work_done:
        try:
            print(">>> Cliente: esperando paquete del servidor...")
            sock.settimeout(5.0)
            pkg, addr = sock.recvfrom(1024)
            print(f">>> Cliente: recibí paquete de {len(pkg)} bytes")
        except socket.timeout:
            print(">>> Cliente: timeout esperando paquetes del servidor")
            break

        flag_end, data_len, pkg_id, data = arch.recv_pckg_go_back_n(pkg)
        print(f">>> Cliente: recibí flag_end={flag_end}, esperado={seq_expected}, pkg_id={pkg_id}, len={data_len}")

        if flag_end == 1:
            print(">>> Cliente: transferencia finalizada.")
            work_done = True
            sock.sendto(seq_expected.to_bytes(4, "big"), server_addr)  # ACK de 4 bytes
            arch.archivo.close()
            break

        if pkg_id == seq_expected:
            arch.archivo.write(data)
            arch.archivo.flush()
            sock.sendto(seq_expected.to_bytes(4, "big"), server_addr)
            print(f">>> Cliente: mando ACK{seq_expected}")
            seq_expected += 1
        else:
            sock.sendto((seq_expected - 1).to_bytes(4, "big"), server_addr)
            print(f">>> Cliente: paquete fuera de orden, reenvío ACK{seq_expected - 1}")