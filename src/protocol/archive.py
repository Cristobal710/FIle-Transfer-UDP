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

    def next_pkg(self):
        msg = self.archivo.read(SIZE_PKG)
        if not msg:
            return None

        header = SIZE_PKG.to_bytes(4, "big")  # + self.last_byte_sent.to_bytes(4, 'big')
        pkg = header + msg
        return pkg


class ArchiveRecv:
    def __init__(
        self,
        path,
    ):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.archivo = open(path, "wb+")

    def recv_pckg(self, msg):
        # sz_msg = int.from_bytes(msg[0:4], 'big')
        pkg = msg[4:]
        self.archivo.write(pkg)
        self.archivo.flush()
