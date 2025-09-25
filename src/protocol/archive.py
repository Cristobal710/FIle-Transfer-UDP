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
        self.last_pkg_sent = 0

    def next_pkg(self, seq_num=0):
        data = self.archivo.read(SIZE_PKG)
        if not data:
            return None

        header = seq_num.to_bytes(1, "big")           
        header += len(data).to_bytes(2, "big") 
        pkg = header + data
        return pkg

    def next_pkg_go_back_n(self, seq_num=0):
        data = self.archivo.read(SIZE_PKG)
        if not data:
            return None, None

        header = seq_num.to_bytes(1, "big")             # its ACK or no
        header += len(data).to_bytes(2, "big")          # size of the pkg data
        pkg_id = self.last_pkg_sent.to_bytes(4, "big")
        header += pkg_id                                # identifier of package 
        pkg = header + data
        self.last_pkg_sent += 1
        return pkg, pkg_id


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

    def recv_pckg_go_back_n(self, msg):
        seq_num = msg[0]
        data_len = int.from_bytes(msg[1:3], "big") 
        pkg_id = int.from_bytes(msg[3:7], "big")
        data = msg[7:7+data_len]

        return seq_num, data_len, pkg_id, data