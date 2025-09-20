import socket
import threading
import queue
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constants import (
    ACK, UPLOAD, DOWNLOAD, END, TUPLA_DIR, UDP_IP, UDP_PORT
)
from protocol.archive import ArchiveRecv, ArchiveSender


def manage_client(channel: queue.Queue, addr, sock: socket):
    conexion_type = channel.get(block=True)

    sock.sendto(ACK.encode(), addr)  # ACK de conexion_type
    name = channel.get(block=True)

    while name == conexion_type:  # entonces el ACK se perdio, reenviamos
        sock.sendto(ACK.encode(), addr)
        name = channel.get(block=True)

    name = name.decode()
    pkg = channel.get(block=True)

    while name == pkg:  # nuevamente, el ACK no llego, tenemos que reenviarlo
        sock.sendto(ACK.encode(), addr)
        pkg = channel.get(block=True)

    if conexion_type == UPLOAD.encode():
        path = f"storage/{name}"
        arch = ArchiveRecv(path)

        seq_expected = 0
        work_done = False
        while not work_done:
            pkg = channel.get(block=True)

            if pkg == END.encode():
                work_done = True
                sock.sendto(f"ACK{seq_expected}".encode(), addr)
                break
            
            seq_num = pkg[0]
            data_len = int.from_bytes(pkg[1:3], "big")
            data = pkg[3:3+data_len]

            if seq_num == seq_expected: #es el esperado, lo escribo
                arch.archivo.write(data)
                arch.archivo.flush()
                sock.sendto(f"ACK{seq_num}".encode(), addr)
                seq_expected = 1 - seq_expected  # alterno
            else: # Duplicado, reenvío ACK del último válido, pero ya lo procesé
                sock.sendto(f"ACK{1 - seq_expected}".encode(), addr)

    elif conexion_type == DOWNLOAD.encode():
        name = channel.get(block=True)
        name = name.decode()
        path = f"storage/{name}"
        arch = ArchiveSender(path)
        end = False
        while not end:
            pkg = arch.next_pkg()
            if pkg is None:
                pkg = END.encode()
                end = True

            sock.sendto(pkg, addr)
            ack_recv = False
            while not ack_recv:
                try:
                    pkg = channel.get(block=True, timeout=0.2)
                    ack_recv = True
                except queue.Empty:
                    sock.sendto(pkg, addr)


class Server:
    def __init__(self, udp_ip, udp_port, path):
        self.udp_ip = udp_ip
        self.udp_port = udp_port
        # self.dir_path = path
        self.clients = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(TUPLA_DIR)
        print(TUPLA_DIR)

    def _listen(self):
        # Listens for messages. If it receives a new client, it adds it to the clients map;
        # otherwise, it forwards the message to the client's thread.    def listen(self):
        while True:
            pkg, addr = self.sock.recvfrom(1024)
            if addr in self.clients:
                self.clients[addr][0].put(pkg)
                if pkg == END.encode():
                    self.clients[addr][1].join()
                    del self.clients[addr]
            else:
                self.start_client(pkg, addr)

    # Start a thread that encapsulates the client with a channel for comunication
    def start_client(self, msg, addr):
        chan = queue.Queue()
        t = threading.Thread(target=manage_client, args=(chan, addr, self.sock))
        t.start()
        self.clients[addr] = [chan, t]
        chan.put(msg)


if __name__ == "__main__":
    server = Server(UDP_IP, UDP_PORT, "hola")
    server._listen()
