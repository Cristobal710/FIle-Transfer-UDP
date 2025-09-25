import socket
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constants import TUPLA_DIR_CLIENT, PROTOCOLO, DOWNLOAD, STOP_AND_WAIT, UPLOAD, GO_BACK_N
from protocol.protocol import handshake, download_stop_and_wait, upload_stop_and_wait
from protocol.archive import ArchiveRecv, ArchiveSender
from utils import upload_go_back_n

def download_file(sock: socket, end, protocolo=PROTOCOLO):
    name = input("Nombre del archivo: ")
    path = input("Path to save file: ")

    handshake(sock, name, DOWNLOAD)
    arch = ArchiveRecv(path)

    if protocolo == STOP_AND_WAIT:
        download_stop_and_wait(sock, arch, end)
    #elif protocolo == GO_BACK_N:
    #    download_go_back_n(sock, arch, end, window_size=4)

def upload_file(sock: socket, end, protocolo=PROTOCOLO):
    name = input("Nombre del archivo: ")
    path = input("Path: ")

    handshake(sock, name, UPLOAD)
    arch = ArchiveSender(path)

    if protocolo == STOP_AND_WAIT:
        upload_stop_and_wait(sock, arch, end)
    elif protocolo == GO_BACK_N:
        upload_go_back_n(sock, arch, end, window_sz=4)

if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(TUPLA_DIR_CLIENT)
    end = False
    # while (not end):
    type_conexion = input("Elegir Upload o Download (Escribir U o D para elegir): ")
    if type_conexion == "D":
        download_file(sock, end, protocolo=PROTOCOLO)
    elif type_conexion == "U":
        upload_file(sock, end, protocolo=PROTOCOLO)

    sock.close()