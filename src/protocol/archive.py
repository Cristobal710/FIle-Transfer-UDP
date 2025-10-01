import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constants import SIZE_PKG


class ArchiveSender:
    """
    Clase para enviar archivos en paquetes UDP
    Maneja el empaquetado de datos según el protocolo (SW o GBN)
    """
    
    def __init__(self, path):
        """
        Inicializa el sender de archivos
        
        Args:
            path: Ruta del archivo a enviar
        """
        self.archivo = open(path, "rb")
        self.last_pkg_sent = 0
        self.archivo.seek(0)
        print(f"ArchiveSender inicializado: last_pkg_sent = {self.last_pkg_sent}, posicion={self.archivo.tell()}")

    def next_pkg(self, seq_num=0):
        """
        Genera el siguiente paquete para Stop and Wait
        
        Args:
            seq_num: Número de secuencia (0 o 1)
            
        Returns:
            bytes: Paquete formateado o None si no hay más datos
        """
        posicion_antes = self.archivo.tell()
        data = self.archivo.read(SIZE_PKG)
        posicion_despues = self.archivo.tell()
        
        if not data:
            return None

        header = seq_num.to_bytes(1, "big")           
        header += len(data).to_bytes(2, "big") 
        pkg = header + data
        
        primer_byte = pkg[0]
        print(f"next_pkg: seq_num={seq_num}, pos_antes={posicion_antes}, pos_despues={posicion_despues}, data_len={len(data)}, pkg_len={len(pkg)}, primer_byte={primer_byte}")
        return pkg

    def next_pkg_go_back_n(self, seq_num=0):
        """
        Genera el siguiente paquete para Go Back N
        
        Args:
            seq_num: Número de secuencia (0 o 1)
            
        Returns:
            tuple: (paquete, pkg_id) o (None, None) si no hay más datos
        """
        data = self.archivo.read(SIZE_PKG)
        if not data:
            return None, None

        pkg_id = self.last_pkg_sent.to_bytes(4, "big")
        self.last_pkg_sent += 1
        
        header = seq_num.to_bytes(1, "big")             # seq_num flag
        header += len(data).to_bytes(2, "big")          # tamaño de datos
        header += pkg_id                                
        pkg = header + data
        print(f"next_pkg_go_back_n: last_pkg_sent={self.last_pkg_sent-1}, pkg_id={int.from_bytes(pkg_id, 'big')}")
        return pkg, pkg_id


class ArchiveRecv:
    """
    Clase para recibir archivos en paquetes UDP
    Maneja el desempaquetado de datos según el protocolo (SW o GBN)
    """
    
    def __init__(self, path):
        """
        Inicializa el receptor de archivos
        
        Args:
            path: Ruta donde guardar el archivo recibido
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.archivo = open(path, "wb")

    def recv_pckg(self, msg):
        """
        Desempaqueta un paquete de Stop and Wait
        
        Args:
            msg: Paquete recibido
            
        Returns:
            tuple: (seq_num, data_len, data)
        """
        seq_num = msg[0]
        data_len = int.from_bytes(msg[1:3], "big") 
        data = msg[3:3+data_len]
        
        print(f"recv_pckg: msg_len={len(msg)}, primer_byte={msg[0]}, seq_num={seq_num}, data_len={data_len}")
        
        return seq_num, data_len, data

    def recv_pckg_go_back_n(self, msg):
        """
        Desempaqueta un paquete de Go Back N
        
        Args:
            msg: Paquete recibido
            
        Returns:
            tuple: (seq_num, data_len, pkg_id, data)
        """
        seq_num = msg[0]
        data_len = int.from_bytes(msg[1:3], "big") 
        pkg_id = int.from_bytes(msg[3:7], "big")
        data = msg[7:7+data_len]
        return seq_num, data_len, pkg_id, data