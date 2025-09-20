import socket
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constants import (
    UPLOAD, DOWNLOAD, TUPLA_DIR_ENVIO, END, ACK, ACK_TIMEOUT
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

def upload_file(sock: socket, end):
    name = input("Nombre del archivo: ")
    path = input("Path: ")
    arch = ArchiveSender(path)


    stop_and_wait(sock, UPLOAD.encode(), TUPLA_DIR_ENVIO) # send type of conexion to server
    stop_and_wait(sock, name.encode(), TUPLA_DIR_ENVIO) # send file name to server

    seq_num = 0
    while not end:
        pkg = arch.next_pkg(seq_num)
        if pkg is None:
            pkg = END.encode()
            end = True

        stop_and_wait(sock, pkg, TUPLA_DIR_ENVIO)
        seq_num = 1 - seq_num  # 0 o 1

def download_file(sock: socket, end):
    name = input("Nombre del archivo: ")
    path = input("Path to save file: ")

    stop_and_wait(sock, DOWNLOAD.encode(), TUPLA_DIR_ENVIO) # send type of conexion to server
    stop_and_wait(sock, name.encode(), TUPLA_DIR_ENVIO) # send file name to server
    arch = ArchiveRecv(path)

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

