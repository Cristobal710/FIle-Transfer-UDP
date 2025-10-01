import socket
from protocol.archive import ArchiveSender, ArchiveRecv
from constants import END, ACK_TIMEOUT, TUPLA_DIR_ENVIO, WINDOW_SIZE

"""
Handshake
1. Send type of conexion to server (UPLOAD or DOWNLOAD)
2. Server sends ACK
3. Send file name to server
4. Server sends ACK
"""
def handshake(sock: socket, name: str, type: str):
    stop_and_wait(sock, type.encode(), TUPLA_DIR_ENVIO) # send type of conexion to server
    stop_and_wait(sock, name.encode(), TUPLA_DIR_ENVIO) # send file name to server
  
"""
Stop and Wait Upload
1. Send pkg
2. Server sends ACK
3. If ACK is not received, resend pkg
4. Repeat until end of file
"""
def upload_stop_and_wait(sock: socket, arch: ArchiveSender, end):
    seq_num = 0
    while not end:
        pkg = arch.next_pkg(seq_num)
        if pkg is None:
            pkg = END.encode()
            end = True

        stop_and_wait(sock, pkg, TUPLA_DIR_ENVIO)
        seq_num = 1 - seq_num  # 0 o 1

"""
Stop and Wait Download
1. Server sends pkg
2. Client sends ACK
3. If ACK is not received, resend pkg
4. Repeat until end of file
"""
def download_stop_and_wait(sock: socket, arch: ArchiveRecv, end):
    seq_expected = 0
    work_done = False
    print(">>> Cliente: empezando a recibir archivo...")

    while not work_done:
        try:
            print(">>> Cliente: esperando paquete del servidor...")
            sock.settimeout(5.0)  # Timeout de 5 segundos
            pkg, addr = sock.recvfrom(1024)
            print(f">>> Cliente: recibí paquete de {len(pkg)} bytes")
        except socket.timeout:
            print(">>> Cliente: timeout esperando paquetes del servidor")
            break

        if pkg == END.encode():
            print(">>> Cliente: transferencia finalizada.")
            work_done = True
            sock.sendto(f"ACK{seq_expected}".encode(), addr)
            arch.archivo.close()
            break

        seq_num, data_len, data = arch.recv_pckg(pkg)
        print(f">>> Cliente: recibí seq={seq_num}, esperado={seq_expected}, len={data_len}")


        if seq_num == seq_expected:
            arch.archivo.write(data)
            arch.archivo.flush()
            sock.sendto(f"ACK{seq_num}".encode(), addr)
            print(f">>> Cliente: mando ACK{seq_num}")
            seq_expected = 1 - seq_expected
        else:
            sock.sendto(f"ACK{1 - seq_expected}".encode(), addr)
            print(f">>> Cliente: paquete duplicado, reenvío ACK{1 - seq_expected}")

"""
Stop and Wait simple packagesender
1. Send msg
2. Server sends ACK
3. If ACK is not received, resend msg
4. Repeat until ack is received
"""
def stop_and_wait(sock: socket, msg, addr):
    sock.sendto(msg, addr)
    ack_recv = False
    while not ack_recv:
        sock.settimeout(ACK_TIMEOUT)
        try:
            pkg, addr = sock.recvfrom(1024)
            # Verificar que sea un ACK válido
            if pkg.startswith(b"ACK"):
                ack_recv = True
                print(f"ACK recibido: {pkg.decode()}")
            else:
                print(f"Paquete no es ACK: {pkg}")
        except socket.timeout:
            print("timeout, no recibi ACK")
            sock.sendto(msg, addr)

"""
Go Back N Upload
1. Send pkg until window_sz is reached
2. Server sends ACK
3. If ACK is not received, resend all pkgs since the last ack received
4. Repeat until end of file
"""
def upload_go_back_n(sock: socket, arch: ArchiveSender, end, window_sz):
    """
    Go Back N Upload - Cliente envía archivo al servidor con ventana deslizante
    """
    send_base = 0
    next_seq_num = 0
    unacked_packets = {}  # {pkg_id: (pkg, send_time)}
    packet_count = 0
    
    print(f"upload_go_back_n: empezando con window_sz={window_sz}")
    
    # Hilo para recibir ACKs
    import threading
    import time
    
    def ack_listener():
        nonlocal send_base
        while True:
            try:
                sock.settimeout(0.1)
                ack_data, addr = sock.recvfrom(1024)
                if len(ack_data) == 4:
                    ack_num = int.from_bytes(ack_data, "big")
                    print(f"ACK recibido: {ack_num}")
                    
                    # Marcar paquetes como confirmados
                    to_remove = []
                    for pkg_id in unacked_packets:
                        if pkg_id <= ack_num:
                            to_remove.append(pkg_id)
                    
                    for pkg_id in to_remove:
                        del unacked_packets[pkg_id]
                    
                    # Actualizar send_base
                    send_base = max(send_base, ack_num + 1)
                    print(f"send_base actualizado a: {send_base}")
            except socket.timeout:
                continue
            except:
                break
    
    # Iniciar hilo de ACKs
    ack_thread = threading.Thread(target=ack_listener, daemon=True)
    ack_thread.start()
    
    # Bucle principal corregido
    while True:
        # Enviar paquetes hasta llenar la ventana
        while next_seq_num < send_base + window_sz and not end:
            pkg, pkg_id = arch.next_pkg_go_back_n(0)  # seq_num no es importante para Go Back N
            packet_count += 1
            
            if pkg is None:
                pkg = END.encode()
                pkg_id = 0
                end = True
                print("upload_go_back_n: enviando END")
            else:
                print(f"upload_go_back_n: paquete #{packet_count}, seq_num={next_seq_num}, pkg_id={int.from_bytes(pkg_id, 'big')}")
            
            sock.sendto(pkg, TUPLA_DIR_ENVIO)
            unacked_packets[int.from_bytes(pkg_id, 'big')] = (pkg, time.time())
            next_seq_num += 1
        
        # Si no hay paquetes sin confirmar y terminamos, salir
        if not unacked_packets and end:
            print("upload_go_back_n: transferencia completada")
            break
        
        # Verificar timeouts
        current_time = time.time()
        timeout_packets = []
        for pkg_id, (pkg, send_time) in unacked_packets.items():
            if current_time - send_time > ACK_TIMEOUT:
                timeout_packets.append(pkg_id)
        
        # Si hay timeouts, reenviar todos los paquetes desde el más antiguo sin confirmar
        if timeout_packets:
            min_unacked = min(unacked_packets.keys())
            print(f"Timeout detectado, reenviando desde paquete {min_unacked}")
            # Reenviar todos los paquetes desde el más antiguo
            for pkg_id in sorted(unacked_packets.keys()):
                pkg, _ = unacked_packets[pkg_id]
                sock.sendto(pkg, TUPLA_DIR_ENVIO)
                unacked_packets[pkg_id] = (pkg, current_time)
                print(f"Reenviando paquete {pkg_id}")
        
        time.sleep(0.001)  # Pequeña pausa para evitar saturar

def download_go_back_n(sock: socket, arch: ArchiveRecv, end, window_sz=WINDOW_SIZE):
    """
    Go Back N Download - Cliente recibe archivo del servidor
    """
    expected_pkg_id = 0
    work_done = False
    print(">>> Cliente: empezando a recibir archivo con Go Back N...")

    while not work_done:
        try:
            print(">>> Cliente: esperando paquete del servidor...")
            sock.settimeout(5.0)  # Timeout de 5 segundos
            pkg, addr = sock.recvfrom(1024)
            print(f">>> Cliente: recibí paquete de {len(pkg)} bytes")
        except socket.timeout:
            print(">>> Cliente: timeout esperando paquetes del servidor")
            break

        if pkg == END.encode():
            print(">>> Cliente: transferencia finalizada.")
            work_done = True
            sock.sendto(expected_pkg_id.to_bytes(4, "big"), addr)
            arch.archivo.close()
            break

        # Parsear paquete Go Back N
        seq_num, data_len, pkg_id, data = arch.recv_pckg_go_back_n(pkg)
        print(f">>> Cliente: recibí seq={seq_num}, esperado={expected_pkg_id}, pkg_id={pkg_id}, len={data_len}")

        if pkg_id == expected_pkg_id:
            # Paquete correcto: escribir datos y enviar ACK
            arch.archivo.write(data)
            arch.archivo.flush()
            sock.sendto(expected_pkg_id.to_bytes(4, "big"), addr)
            print(f">>> Cliente: mando ACK{expected_pkg_id}")
            expected_pkg_id += 1
        else:
            # Paquete fuera de orden: reenviar ACK del último válido
            ack_to_send = max(0, expected_pkg_id - 1)
            sock.sendto(ack_to_send.to_bytes(4, "big"), addr)
            print(f">>> Cliente: paquete fuera de orden, reenvío ACK{ack_to_send}")