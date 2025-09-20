import socket
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constants import (
    UPLOAD, DOWNLOAD, TUPLA_DIR_ENVIO, END, ACK, ACK_TIMEOUT, PROTOCOLO, STOP_AND_WAIT, GO_BACK_N
)
from protocol.archive import ArchiveSender, ArchiveRecv

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

def upload_stop_and_wait(sock: socket, arch: ArchiveSender, end):
    seq_num = 0
    while not end:
        pkg = arch.next_pkg(seq_num)
        if pkg is None:
            pkg = END.encode()
            end = True

        stop_and_wait(sock, pkg, TUPLA_DIR_ENVIO)
        seq_num = 1 - seq_num  # 0 o 1

def upload_file(sock: socket, end, protocolo=PROTOCOLO):
    name = input("Nombre del archivo: ")
    path = input("Path: ")

    stop_and_wait(sock, UPLOAD.encode(), TUPLA_DIR_ENVIO) # send type of conexion to server
    stop_and_wait(sock, name.encode(), TUPLA_DIR_ENVIO) # send file name to server
    arch = ArchiveSender(path)

    if protocolo == STOP_AND_WAIT:
        upload_stop_and_wait(sock, arch, end)
    elif protocolo == GO_BACK_N:
        upload_go_back_n(sock, arch, end, window_size=4)

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


def download_file(sock: socket, end, protocolo=PROTOCOLO):
    name = input("Nombre del archivo: ")
    path = input("Path to save file: ")

    stop_and_wait(sock, DOWNLOAD.encode(), TUPLA_DIR_ENVIO) # send type of conexion to server
    stop_and_wait(sock, name.encode(), TUPLA_DIR_ENVIO) # send file name to server
    arch = ArchiveRecv(path)

    if protocolo == STOP_AND_WAIT:
        download_stop_and_wait(sock, arch, end)
    elif protocolo == GO_BACK_N:
        download_go_back_n(sock, arch, end, window_size=4)


def upload_go_back_n(sock: socket, arch: ArchiveSender, end, window_size):
    base = 0
    next_seq_num = 0
    window = {} #guardo los que estan espersndo a ser ackeados

    sock.settimeout(None)   # arranca sin temporizador

    while not end or base < next_seq_num:
        
        while next_seq_num < base + window_size and not end: # mando paquetes mientras haya espacio en la ventana
            pkg = arch.next_pkg(next_seq_num)
            if pkg is None:       # ya vio todo el archivo
                pkg = END.encode()
                end = True

            sock.sendto(pkg, TUPLA_DIR_ENVIO)
            print(f">>> Envié paquete {next_seq_num}")
            window[next_seq_num] = pkg

            if base == next_seq_num:# si es el primer paquete pendiente → arranco temporizador
                sock.settimeout(ACK_TIMEOUT)

            next_seq_num += 1

        try: # espero que llegue el ACK
            ack_msg, _ = sock.recvfrom(1024)
            ack_num = int(ack_msg.decode().replace("ACK", ""))
            print(f">>> Recibí ACK{ack_num}")

            base = ack_num + 1 # la nueva base depende el numero de ACK q recibo

            if base == next_seq_num: # ventana vacía → paro temporizador
                sock.settimeout(None)
            else:
                sock.settimeout(ACK_TIMEOUT)

        except socket.timeout:
            print("Timeout, reenvío ventana...")
            
            for seq in range(base, next_seq_num): # retransmite todos los paquetes pendientes
                sock.sendto(window[seq], TUPLA_DIR_ENVIO)
                print(f">>> Reenvié paquete {seq}")
            sock.settimeout(ACK_TIMEOUT)



def download_go_back_n(sock: socket, arch: ArchiveRecv, end, window_size):
    expected_seq_num = 0
    work_done = False

    while not work_done:
        pkg, addr = sock.recvfrom(1024)

        if pkg == END.encode():#ya se envio todo el archivo
            print(">>> Cliente: transferencia finalizada.")
            work_done = True
           
            sock.sendto(f"ACK{expected_seq_num}".encode(), addr) # mando ACK final
            arch.archivo.close()
            break

        
        seq_num, data_len, data = arch.recv_pckg(pkg) # siguen habiendo paquetes
        print(f">>> Recibí paquete seq={seq_num}, esperado={expected_seq_num}, len={data_len}")

        if seq_num == expected_seq_num:
           
            arch.archivo.write(data) # paquete correcto → lo escribo y confirmo
            arch.archivo.flush()
            sock.sendto(f"ACK{seq_num}".encode(), addr)
            print(f">>> Envío ACK{seq_num}")
            expected_seq_num += 1
        else:
            # paquete fuera de orden → descartar y repetir último ACK válido
            sock.sendto(f"ACK{expected_seq_num - 1}".encode(), addr)
            print(f">>> Paquete fuera de orden, reenvío ACK{expected_seq_num - 1}")
