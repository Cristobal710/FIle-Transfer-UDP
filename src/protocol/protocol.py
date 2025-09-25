import socket
from protocol.archive import ArchiveSender, ArchiveRecv
from constants import END, ACK_TIMEOUT, TUPLA_DIR_ENVIO

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

    while not work_done:
        pkg, addr = sock.recvfrom(1024)

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
            ack_recv = True
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
    seq_num = 0
    pkgs_not_ack = {}

    
    while not end:
        while(len(pkgs_not_ack) != window_sz and not end):
            pkg, pkg_id = arch.next_pkg_go_back_n(seq_num)
            if pkg is None:
                pkg = END.encode()
                end = True
            sock.sendto(pkg, TUPLA_DIR_ENVIO)
            pkgs_not_ack[pkg_id] = pkg
            
        print("termine de enviar los paquetes, tengo que esperar ACK")
        sock.settimeout(ACK_TIMEOUT)
        try:
            pkg, addr = sock.recvfrom(1024)
            print(f"recibi el ACK del paquete: {pkg}")
            if (pkg in pkgs_not_ack.keys()):
                del pkgs_not_ack[pkg]

        except socket.timeout:
            print("timeout, no recibi ACKs, reenvio los n paquetes")
            for value in pkgs_not_ack.values():
                sock.sendto(value, addr)