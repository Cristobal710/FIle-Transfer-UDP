import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constants import SIZE_PKG


class ArchiveSender:
    def __init__(
        self,
        path,
    ):
        self.archivo = open(path, "rb")
        self.last_byte_sent = 0

    def next_pkg(self, seq_num=0):
        data = self.archivo.read(SIZE_PKG)
        if not data:
            return None

        header = seq_num.to_bytes(1, "big")           
        header += len(data).to_bytes(2, "big") 
        pkg = header + data
        return pkg


class ArchiveRecv:
    def __init__(
        self,
        path,
    ):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.archivo = open(path, "wb")

    def recv_pckg(self, msg):
        seq_num = msg[0]
        data_len = int.from_bytes(msg[1:3], "big") 
        data = msg[3:3+data_len]

        return seq_num, data_len, data