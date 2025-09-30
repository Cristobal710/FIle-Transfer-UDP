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
from protocol.protocol import upload_file, download_file, PacketReader


def upload_from_client(name, channel: queue.Queue, sock: socket, addr, protocolo="SW"):
    """
    Maneja subida de archivo desde cliente usando funciones unificadas
    
    Args:
        name: Nombre del archivo
        channel: Cola de comunicación
        sock: Socket UDP
        addr: Dirección del cliente
        protocolo: Protocolo a usar ("SW" o "GBN")
    """
    path = f"src/server/storage/{name}"
    arch = ArchiveRecv(path)
    
    if protocolo == "SW":
        receive_stop_and_wait_server(sock, arch, addr)
    else: 
        receive_go_back_n_server(sock, arch, addr)


def manage_client(channel: queue.Queue, addr, sock: socket):
    conexion_type = channel.get(block=True)

    sock.sendto(ACK.encode(), addr)  # ACK de conexion_type
    name = channel.get(block=True)

    while name == conexion_type:  # entonces el ACK se perdió, reenviamos
        sock.sendto(ACK.encode(), addr)
        name = channel.get(block=True)

    name = name.decode()
    
    # Enviar ACK del nombre del archivo
    sock.sendto(ACK.encode(), addr)
    
    if conexion_type == UPLOAD.encode():
        # Para upload, detectar protocolo basado en el primer paquete de datos
        pkg = channel.get(block=True)
        protocolo = detect_protocol(pkg)
        print(f"Protocolo detectado: {protocolo}")
        upload_from_client(name, channel, sock, addr, protocolo)
    elif conexion_type == DOWNLOAD.encode():
        # Para download, usar Stop and Wait por defecto (más simple)
        print("Iniciando download con Stop and Wait")
        download_from_client(name, channel, sock, addr, "SW")

def detect_protocol(pkg):
    """
    Detecta el protocolo basado en el formato del paquete
    
    Args:
        pkg: Primer paquete recibido
        
    Returns:
        str: "SW" o "GBN"
    """
    # Stop and Wait: seq_num (1 byte) + data_len (2 bytes) + data
    # Go Back N: seq_num (1 byte) + data_len (2 bytes) + pkg_id (4 bytes) + data
    
    if len(pkg) >= 7:
        # Verificar si tiene pkg_id (4 bytes después de seq_num y data_len)
        data_len = int.from_bytes(pkg[1:3], "big")
        expected_sw_len = 3 + data_len  # 1 + 2 + data_len
        expected_gbn_len = 7 + data_len  # 1 + 2 + 4 + data_len
        
        if len(pkg) == expected_sw_len:
            return "SW"
        elif len(pkg) == expected_gbn_len:
            return "GBN"
        else:
            # Por defecto, si tiene 7+ bytes, asumir GBN
            return "GBN"
    else:
        return "SW"
        
def download_from_client(name, channel: queue.Queue, sock: socket, addr, protocolo="SW"):
    """
    Maneja descarga de archivo a cliente usando funciones unificadas

    Args:
        name: Nombre del archivo
        channel: Cola de comunicación
        sock: Socket UDP
        addr: Dirección del cliente
        protocolo: Protocolo a usar ("SW" o "GBN")
    """
    # name ya es un string, no necesita decode
    path = f"src/server/storage/{name}"
    
    # Verificar que el archivo existe
    if not os.path.exists(path):
        print(f"Archivo no encontrado: {path}")
        return
    
    print(f"Iniciando envío de archivo: {path}")
    arch = ArchiveSender(path)

    # Usar función unificada de upload (servidor envía = upload)
    upload_file(sock, arch, addr, protocolo)

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
            pkg, addr = self.sock.recvfrom(2048)  # Buffer más grande para paquetes grandes
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


def receive_stop_and_wait_server(sock: socket, arch: ArchiveRecv, sender_addr):
    """
    Stop and Wait - Lado que RECIBE (servidor) simple y rápido
    """
    seq_expected = 0
    work_done = False
    packet_count = 0

    while not work_done:
        try:
            pkg, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue

        if pkg == END.encode():
            print(f">>> Transferencia finalizada. Total paquetes recibidos: {packet_count}")
            work_done = True
            sock.sendto(f"ACK{seq_expected}".encode(), sender_addr)
            arch.archivo.close()
            break

        packet_count += 1
        seq_num, data_len, data = arch.recv_pckg(pkg)
        print(f">>> Paquete #{packet_count}: seq={seq_num}, esperado={seq_expected}, len={data_len}")

        if seq_num == seq_expected:
            # Enviar ACK INMEDIATAMENTE (antes de escribir)
            sock.sendto(f"ACK{seq_num}".encode(), sender_addr)
            print(f">>> Mando ACK{seq_num} a {sender_addr}")
            
            # Escribir datos después del ACK
            arch.archivo.write(data)
            # Flush cada 10 paquetes para mejor rendimiento
            if packet_count % 10 == 0:
                arch.archivo.flush()
            
            seq_expected = 1 - seq_expected
        else:
            sock.sendto(f"ACK{1 - seq_expected}".encode(), sender_addr)
            print(f">>> Paquete duplicado, reenvío ACK{1 - seq_expected} a {sender_addr}")

def receive_go_back_n_server(sock: socket, arch: ArchiveRecv, sender_addr):
    """
    Go Back N - Lado que RECIBE (servidor) con buffer de recepción y procesamiento en paralelo
    """
    import threading
    import queue as q
    import time
    
    expected_seq = 0
    work_done = False
    packet_count = 0
    data_queue = q.Queue()
    received_packets = {}  # Buffer para paquetes fuera de orden
    ack_lock = threading.Lock()
    
    def process_data():
        """Procesa los datos en paralelo"""
        while True:
            try:
                data, pkg_id = data_queue.get(timeout=1)
                if data is None:  # Señal de fin
                    break
                arch.archivo.write(data)
                # Solo flush cada 10 paquetes para mejor rendimiento
                if pkg_id % 10 == 0:
                    arch.archivo.flush()
                print(f">>> Procesado paquete pkg_id={pkg_id}")
                data_queue.task_done()
            except q.Empty:
                continue
    
    def send_ack(pkg_id):
        """Envía ACK de forma thread-safe"""
        with ack_lock:
            sock.sendto(pkg_id.to_bytes(4, "big"), sender_addr)
            print(f">>> Enviando ACK{pkg_id} a {sender_addr}")
    
    # Iniciar thread de procesamiento
    processor = threading.Thread(target=process_data)
    processor.start()

    while not work_done:
        try:
            pkg, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue

        if pkg == END.encode():
            print(f">>> Transferencia finalizada. Total paquetes recibidos: {packet_count}")
            work_done = True
            send_ack(expected_seq)
            data_queue.put((None, None))  # Señal de fin
            processor.join()
            arch.archivo.close()
            break

        packet_count += 1
        seq_num, data_len, pkg_id, data = arch.recv_pckg_go_back_n(pkg)
        print(f">>> Paquete #{packet_count}: seq={seq_num}, esperado={expected_seq}, pkg_id={pkg_id}, len={data_len}")

        if pkg_id == expected_seq:
            # Paquete en orden: procesar inmediatamente
            send_ack(expected_seq)
            data_queue.put((data, pkg_id))
            expected_seq += 1
            
            # Procesar paquetes en buffer que ahora están en orden
            while expected_seq in received_packets:
                buffered_data, buffered_pkg_id = received_packets.pop(expected_seq)
                send_ack(expected_seq)
                data_queue.put((buffered_data, buffered_pkg_id))
                expected_seq += 1
                
        elif pkg_id > expected_seq:
            # Paquete futuro: guardar en buffer
            received_packets[pkg_id] = (data, pkg_id)
            ack_to_send = max(0, expected_seq - 1)
            send_ack(ack_to_send)
            print(f">>> Paquete futuro pkg_id={pkg_id}, guardado en buffer")
        else:
            # Paquete duplicado o muy viejo: reenviar ACK
            ack_to_send = max(0, expected_seq - 1)
            send_ack(ack_to_send)
            print(f">>> Paquete duplicado pkg_id={pkg_id}, reenviando ACK{ack_to_send}")

if __name__ == "__main__":
    server = Server(UDP_IP, UDP_PORT, "hola")
    server._listen()
