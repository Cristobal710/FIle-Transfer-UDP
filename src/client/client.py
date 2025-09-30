import socket
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constants import TUPLA_DIR_CLIENT, TUPLA_DIR_ENVIO, PROTOCOLO, DOWNLOAD, STOP_AND_WAIT, UPLOAD, GO_BACK_N
from protocol.protocol import handshake, upload_file, download_file, PacketReader, receive_stop_and_wait, receive_go_back_n
from protocol.archive import ArchiveRecv, ArchiveSender


class UDPClient:
    """
    Cliente UDP para transferencia de archivos
    Maneja la conexión y operaciones con el servidor
    """
    
    def __init__(self, protocolo=PROTOCOLO):
        """
        Inicializa el cliente
        
        Args:
            protocolo: Protocolo a usar (STOP_AND_WAIT o GO_BACK_N)
        """
        self.protocolo = protocolo
        self.sock = None
        self.connected = False
    
    def connect(self):
        """
        Establece conexión con el servidor
        
        Returns:
            bool: True si conexión exitosa, False si falló
        """
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.connected = True
            print(f"Cliente conectado")
            return True
        except Exception as e:
            print(f"Error conectando: {e}")
            return False
    
    def disconnect(self):
        """Cierra la conexión"""
        if self.sock:
            self.sock.close()
            self.connected = False
            print("Conexión cerrada")
    
    def download_file(self, name, path, end=False):
        """
        Descarga un archivo del servidor
        
        Args:
            name: Nombre del archivo a descargar
            path: Ruta donde guardar el archivo
            end: Flag de control (no usado)
        """
        if not self.connected:
            print("Cliente no conectado")
            return
        
        handshake(self.sock, name, DOWNLOAD)
        arch = ArchiveRecv(path)

        if self.protocolo == STOP_AND_WAIT:
            receive_stop_and_wait(self.sock, arch, TUPLA_DIR_ENVIO)
        else:  
            receive_go_back_n(self.sock, arch, TUPLA_DIR_ENVIO)

    def upload_file(self, name, path, end=False):
        """
        Sube un archivo al servidor
        
        Args:
            name: Nombre del archivo en el servidor
            path: Ruta del archivo local
            end: Flag de control (no usado)
        """
        if not self.connected:
            print("Cliente no conectado")
            return

        handshake(self.sock, name, UPLOAD)
        arch = ArchiveSender(path)
        
        upload_file(self.sock, arch, TUPLA_DIR_ENVIO, self.protocolo)


if __name__ == "__main__":
    client = UDPClient()
    
    if not client.connect():
        exit(1)
    
    try:
        end = False
        type_conexion = input("Elegir Upload o Download (Escribir U o D para elegir): ")
        
        if type_conexion == "D":
            name = input("Nombre del archivo: ")
            path = input("Path to save file: ")
            client.download_file(name, path, end)
            
        elif type_conexion == "U":
            name = input("Nombre del archivo: ")
            path = input("Path: ")
            client.upload_file(name, path, end)
    
    finally:
        client.disconnect()