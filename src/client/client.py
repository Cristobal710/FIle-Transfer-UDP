import socket
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constants import TUPLA_DIR_CLIENT, PROTOCOLO, DOWNLOAD, STOP_AND_WAIT, UPLOAD, GO_BACK_N, WINDOW_SIZE
from protocol.protocol import handshake, download_stop_and_wait, upload_stop_and_wait, upload_go_back_n, download_go_back_n
from protocol.archive import ArchiveRecv, ArchiveSender

def download_file(sock: socket, end, protocolo=PROTOCOLO):
    """
    Descarga un archivo desde el servidor usando el protocolo especificado.
    Solicita al usuario el nombre del archivo y la ruta donde guardarlo.
    """
    name = input("Nombre del archivo: ")
    path = input("Path to save file: ")

    handshake(sock, name, DOWNLOAD)
    arch = ArchiveRecv(path)

    if protocolo == STOP_AND_WAIT:
        download_stop_and_wait(sock, arch, end)
    elif protocolo == GO_BACK_N:
        download_go_back_n(sock, arch, end, window_sz=WINDOW_SIZE)

def upload_file(sock: socket, end, protocolo=PROTOCOLO):
    """
    Sube un archivo al servidor usando el protocolo especificado.
    Solicita al usuario el nombre del archivo y la ruta del archivo a subir.
    """
    name = input("Nombre del archivo: ")
    path = input("Path: ")

    handshake(sock, name, UPLOAD)
    arch = ArchiveSender(path)

    if protocolo == STOP_AND_WAIT:
        upload_stop_and_wait(sock, arch, end)
    elif protocolo == GO_BACK_N:
        upload_go_back_n(sock, arch, end, window_sz=WINDOW_SIZE)

if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(TUPLA_DIR_CLIENT)
    end = False
    type_conexion = input("Elegir Upload o Download (Escribir U o D para elegir): ")
    if type_conexion == "D":
        download_file(sock, end, protocolo=PROTOCOLO)
    elif type_conexion == "U":
        upload_file(sock, end, protocolo=PROTOCOLO)

    sock.close()