import socket
import threading
import queue
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constants import (
    ACK, UPLOAD, DOWNLOAD, END, TUPLA_DIR, UDP_IP, UDP_PORT, PROTOCOLO, STOP_AND_WAIT, GO_BACK_N
)
from protocol.archive import ArchiveRecv, ArchiveSender


def upload_from_client(name, channel: queue.Queue, sock: socket, addr):
    path = f"src/server/storage/{name}"
    arch = ArchiveRecv(path)
    seq_expected = 0
    work_done = False
    while not work_done:
        pkg = channel.get(block=True)
        if pkg == END.encode():
            work_done = True
            sock.sendto(f"ACK{seq_expected}".encode(), addr)
            break
        
        #podemos modularizar esto para que se haga en un metodo, es tratado de pkg
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


def download_from_client_stop_and_wait(name, sock, addr, channel=None):
    """
    Stop and Wait Download - Servidor envía archivo al cliente
    """
    path = f"src/server/storage/{name}"
    if not os.path.exists(path):
        print(f">>> Server: archivo no encontrado: {path}")
        return
    print(f">>> Server: archivo encontrado, empezando envío con Stop and Wait...")
    arch = ArchiveSender(path)
    
    seq_num = 0
    end = False
    
    while not end:
        pkg = arch.next_pkg(seq_num)
        if pkg is None:
            pkg = END.encode()
            end = True
       
        sock.sendto(pkg, addr)
        print(f">>> Server: envió paquete con seq={seq_num} (len={len(pkg)})")

        ack_recv = False
        while not ack_recv:
            try:
                sock.settimeout(0.5)
                ack_data, ack_addr = sock.recvfrom(1024)
                if ack_data.startswith(b"ACK"):
                    ack_num = int(ack_data.decode().replace("ACK", ""))
                    if ack_num == seq_num:
                        print(f">>> Server: recibió ACK{ack_num}")
                        ack_recv = True
                        if not end:
                            seq_num = 1 - seq_num
                    else:
                        print(f">>> Server: ACK incorrecto, esperaba {seq_num}, recibí {ack_num}")
            except socket.timeout:
                print(f">>> Server: timeout esperando ACK{seq_num}, reenvío")
                sock.sendto(pkg, addr)

def download_from_client_go_back_n(name, sock, addr):
    """
    Go Back N Download - Servidor envía archivo al cliente
    """
    path = f"src/server/storage/{name}"
    if not os.path.exists(path):
        print(f">>> Server: archivo no encontrado: {path}")
        return
    print(f">>> Server: archivo encontrado, empezando envío con Go Back N...")
    arch = ArchiveSender(path)
    
    seq_num = 0
    end = False
    
    while not end:
        pkg, pkg_id = arch.next_pkg_go_back_n(0)  # seq_num no es importante para Go Back N
        if pkg is None:
            pkg = END.encode()
            pkg_id = b"END"
            end = True
       
        sock.sendto(pkg, addr)
        print(f">>> Server: envió paquete con seq={seq_num}, pkg_id={int.from_bytes(pkg_id, 'big') if pkg_id != b'END' else 'END'} (len={len(pkg)})")

        ack_recv = False
        while not ack_recv:
            try:
                sock.settimeout(0.5)
                ack_data, ack_addr = sock.recvfrom(1024)
                if len(ack_data) == 4:
                    ack_num = int.from_bytes(ack_data, "big")
                    
                    if ack_num == seq_num:
                        print(f">>> Server: recibió ACK{ack_num}")
                        ack_recv = True
                        if not end:
                            seq_num += 1
                    else:
                        print(f">>> Server: ACK incorrecto, esperaba {seq_num}, recibí {ack_num}")
            except socket.timeout:
                if end:
                    # Si es el paquete END y hay timeout, asumir que el cliente terminó
                    print(">>> Server: Transferencia completada (timeout en END)")
                    return
                print(f">>> Server: timeout esperando ACK{seq_num}, reenvío")
                sock.sendto(pkg, addr)
            except ConnectionResetError:
                print(">>> Server: Conexión reseteada durante download")
                return
            except Exception as e:
                print(f">>> Server: Error durante download: {e}")
                return

def upload_from_client_go_back_n(name, channel, sock, addr):
    path = f"src/server/storage/{name}"
    arch = ArchiveRecv(path)
    seq_expected = 0
    work_done = False
    expected_pkg_id = 0
    while not work_done:
        pkg = channel.get(block=True)
        if pkg == END.encode():
            work_done = True
            sock.sendto(expected_pkg_id.to_bytes(4, "big"), addr)
            break
        
        #podemos modularizar esto para que se haga en un metodo, es tratado de pkg
        seq_num, data_len, pkg_id, data =  arch.recv_pckg_go_back_n(pkg)

        if pkg_id == expected_pkg_id: #es el esperado, lo escribo
            arch.archivo.write(data)
            arch.archivo.flush()
            print(f"sendind this pkg_id to client: {expected_pkg_id}")
            sock.sendto(expected_pkg_id.to_bytes(4, "big"), addr)
            expected_pkg_id += 1
        else: # Duplicado o fuera de orden, reenvío ACK del último válido
            ack_to_send = max(0, expected_pkg_id - 1)
            sock.sendto(ack_to_send.to_bytes(4, "big"), addr)


def manage_client(channel: queue.Queue, addr, sock: socket):
    try:
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
            # Enviar ACK del nombre del archivo
            sock.sendto(ACK.encode(), addr)
            print(f">>> Server: envié ACK del nombre del archivo: {name}")
            
            if PROTOCOLO == STOP_AND_WAIT:
                upload_from_client(name, channel, sock, addr)
            elif PROTOCOLO == GO_BACK_N:
                upload_from_client_go_back_n(name, channel, sock, addr)

        elif conexion_type == DOWNLOAD.encode():
            # name ya fue leído arriba, no necesitamos leerlo de nuevo
            # Enviar ACK del nombre del archivo
            sock.sendto(ACK.encode(), addr)
            print(f">>> Server: envié ACK del nombre del archivo: {name}")
            
            if PROTOCOLO == STOP_AND_WAIT:
                download_from_client_stop_and_wait(name, sock, addr, channel)
            elif PROTOCOLO == GO_BACK_N:
                download_from_client_go_back_n(name, sock, addr)
    except Exception as e:
        print(f">>> Server: Error en manage_client: {e}")
        return


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
        # otherwise, it forwards the message to the client's thread.
        while True:
            try:
                pkg, addr = self.sock.recvfrom(1024)
                if addr in self.clients:
                    self.clients[addr][0].put(pkg)
                    if pkg == END.encode():
                        self.clients[addr][1].join()
                        del self.clients[addr]
                else:
                    self.start_client(pkg, addr)
            except ConnectionResetError:
                print(">>> Server: Conexión reseteada por el cliente")
                continue
            except socket.timeout:
                # Timeout normal, no es un error
                continue
            except Exception as e:
                print(f">>> Server: Error inesperado: {e}")
                continue

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
