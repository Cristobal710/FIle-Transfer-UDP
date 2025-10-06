import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from lib.constants import SIZE_PKG


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
        Formato: [seq_num:1bit][flag_end:1bit][data_len:2bytes][data:variable]
        
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

        # Crear header con seq_num y flag_end en el primer byte
        first_byte = (seq_num << 1) | 0  # flag_end = 0 para datos normales
        header = first_byte.to_bytes(1, "big")
        header += len(data).to_bytes(2, "big")
        pkg = header + data
        
        print(f"next_pkg: seq_num={seq_num}, flag_end=0, pos_antes={posicion_antes}, pos_despues={posicion_despues}, data_len={len(data)}, pkg_len={len(pkg)}")
        return pkg

    def next_pkg_go_back_n(self, seq_num=0):
        """
        Genera el siguiente paquete para Go Back N
        Formato: [flag_end:1bit][data_len:2bytes][pkg_id:4bytes][data:variable]
        
        Args:
            seq_num: Número de secuencia del paquete
            
        Returns:
            tuple: (paquete, pkg_id) o (None, None) si no hay más datos
        """
        data = self.archivo.read(SIZE_PKG)
        if not data:
            return None, None

        pkg_id = seq_num.to_bytes(4, "big")
        
        # Crear header con flag_end en el primer byte
        first_byte = 0  # flag_end = 0 para datos normales
        header = first_byte.to_bytes(1, "big")
        header += len(data).to_bytes(2, "big")          # tamaño de datos
        header += pkg_id                                
        pkg = header + data
        print(f"next_pkg_go_back_n: flag_end=0, seq_num={seq_num}, pkg_id={int.from_bytes(pkg_id, 'big')}")
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
        Formato: [seq_num:1bit][flag_end:1bit][data_len:2bytes][data:variable]
        
        Args:
            msg: Paquete recibido
            
        Returns:
            tuple: (seq_num, flag_end, data_len, data)
        """
        first_byte = msg[0]
        seq_num = (first_byte >> 1) & 1  # Extraer bit 1
        flag_end = first_byte & 1        # Extraer bit 0
        data_len = int.from_bytes(msg[1:3], "big") 
        data = msg[3:3+data_len]
        
        print(f"recv_pckg: msg_len={len(msg)}, primer_byte={msg[0]}, seq_num={seq_num}, flag_end={flag_end}, data_len={data_len}")
        
        return seq_num, flag_end, data_len, data

    def recv_pckg_go_back_n(self, msg):
        """
        Desempaqueta un paquete de Go Back N
        Formato: [flag_end:1bit][data_len:2bytes][pkg_id:4bytes][data:variable]
        
        Args:
            msg: Paquete recibido
            
        Returns:
            tuple: (flag_end, data_len, pkg_id, data)
        """
        first_byte = msg[0]
        flag_end = first_byte & 1        # Extraer bit 0
        data_len = int.from_bytes(msg[1:3], "big") 
        pkg_id = int.from_bytes(msg[3:7], "big")
        data = msg[7:7+data_len]
        return flag_end, data_len, pkg_id, data

    def write_data(self, data):
        self.archivo.write(data)
        self.archivo.flush()