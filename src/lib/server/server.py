import socket
import threading
import queue
import sys
import os
import argparse
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.lib.constants import (
    UPLOAD, DOWNLOAD, STOP_AND_WAIT, GO_BACK_N, ACK_TIMEOUT_SW, ACK_TIMEOUT_GBN, WINDOW_SIZE_GBN, WINDOW_SIZE_SW
)
from src.lib.protocol.archive import ArchiveRecv, ArchiveSender
from src.lib.protocol.utils import setup_logging, create_server_parser


def download_from_client_go_back_n(name, writing_queue: queue.Queue, addr, window_sz, channel, timeout):
    """
    Envía archivo al cliente usando Go Back N.
    Utiliza una ventana deslizante para enviar n paquetes y luego esperar ACKs.
    """
    # Usar path absoluto
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "storage", name)
    if not os.path.exists(path):
        print(f">>> Server: archivo no encontrado: {path}")
        return
    print(f">>> Server: archivo encontrado, empezando envío con Go Back N...")
    arch = ArchiveSender(path)
    
    pkg_id = 3
    pkgs_not_ack = {}
    file_finished = False
    end = False
    
    while not end:
        # Fase 1: Enviar paquetes hasta llenar la ventana o terminar el archivo
        while(len(pkgs_not_ack) < window_sz and not file_finished):
            pkg, pkg_id_bytes = arch.next_pkg_go_back_n(pkg_id)  # Usar pkg_id directamente
            if pkg is None:
                # Crear paquete END con flag_end = 1
                first_byte = 1  # flag_end = 1 para END
                pkg = first_byte.to_bytes(1, "big") + (0).to_bytes(2, "big") + (pkg_id).to_bytes(4, "big")  # data_len = 0, pkg_id = pkg_id
                pkg_id_bytes = (pkg_id).to_bytes(4, "big")  # pkg_id = pkg_id para END
                file_finished = True
                print(f">>> Server: creando paquete END con pkg_id={pkg_id}")
            writing_queue.put((pkg, addr))
            print(f">>> Server: envió paquete con flag_end={pkg[0] & 1}, pkg_id={pkg_id} (len={len(pkg)})")
            
            # Siempre agregar a pkgs_not_ack, incluyendo el paquete END
            pkgs_not_ack[pkg_id_bytes] = pkg
            pkg_id += 1
        
        # Fase 2: Esperar ACKs
        print(f">>> Server: termine de enviar los paquetes, tengo que esperar ACK. Paquetes sin ACK: {len(pkgs_not_ack)}")
        
        try:
            queue_size_before = channel.qsize()
            print(f">>> Server: Cola de {addr} tiene {queue_size_before} paquetes antes de get() en download")
            pkg = channel.get(block=True, timeout=timeout)
            queue_size_after = channel.qsize()
            print(f">>> Server: Cola de {addr} tiene {queue_size_after} paquetes después de get() en download, ACK recibido: {pkg}")
            if len(pkg) == 4:
                ack_num = int.from_bytes(pkg, "big")
                print(f">>> Server: ACK recibido para paquete {ack_num}")
                
                # Remover todos los paquetes con pkg_id <= ack_num
                to_remove = []
                for pkg_id_bytes_key in pkgs_not_ack:
                    pkg_id_num = int.from_bytes(pkg_id_bytes_key, 'big')
                    if pkg_id_num <= ack_num:
                        to_remove.append(pkg_id_bytes_key)
                        print(f">>> Server: removiendo paquete {pkg_id_num} de la ventana")
                
                for pkg_id_bytes_key in to_remove:
                    del pkgs_not_ack[pkg_id_bytes_key]
                
                # Si terminamos el archivo y no hay paquetes sin confirmar, salir
                if file_finished and not pkgs_not_ack:
                    print(">>> Server: todos los paquetes confirmados, finalizando transferencia")
                    end = True

        except queue.Empty:
            if file_finished and not pkgs_not_ack:
                # Si terminamos el archivo y no hay paquetes sin confirmar, salir
                print(">>> Server: timeout pero no hay paquetes pendientes, finalizando")
                end = True
            else:
                print(">>> Server: timeout, no recibi ACKs, reenvio los n paquetes")
                for value in pkgs_not_ack.values():
                    writing_queue.put((value, addr))
        except ConnectionResetError:
                print(">>> Server: Conexión reseteada durante download")
                return
        except Exception as e:
                print(f">>> Server: Error durante download: {e}")
                return

def upload_from_client_go_back_n(name, channel, writing_queue: queue.Queue, addr, protocol=None, sock=None):
    """
    Recibe archivo del cliente usando Go Back N o Stop and Wait.
    Protocol determina la lógica de ACK:
    - STOP_AND_WAIT: ACK del siguiente paquete esperado (pkg_id+1)
    - GO_BACK_N: ACK del último paquete recibido en orden (expected_pkg_id-1) para fuera de orden
    """
    print(f">>> Server: upload_from_client_go_back_n iniciado para {name} desde {addr}")
    # Usar path absoluto
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "storage", name)
    arch = ArchiveRecv(path)
    expected_pkg_id = 3
    work_done = False
    
    print(f">>> Server: upload_from_client_go_back_n esperando paquetes de {addr}")
    
    while not work_done:
        try:
            pkg = channel.get(block=True, timeout=30.0)  # Timeout de 30 segundos
        except queue.Empty:
            print(f">>> Server: Timeout esperando paquetes de {addr}")
            break
        
        flag_end, data_len, pkg_id, data = arch.recv_pckg_go_back_n(pkg)
        
        print(f">>> Server: recibí paquete flag_end={flag_end}, pkg_id={pkg_id}, esperado={expected_pkg_id}")
        
        if pkg_id == expected_pkg_id:
            arch.archivo.write(data)
            arch.archivo.flush()
            
            # Comportamiento diferenciado por protocolo para el último paquete
            ack_data = (pkg_id+1).to_bytes(4, "big")
            if flag_end == 1:
                if protocol == STOP_AND_WAIT:
                    # SW: Envío directo para evitar condiciones de carrera
                    sock.sendto(ack_data, addr)
                    print(f">>> Server: SW - envié ACK{pkg_id+1} FINAL directamente a {addr}")
                else:
                    # GBN: Usar cola + delay (funciona mejor con ventana deslizante)
                    writing_queue.put((ack_data, addr))
                    print(f">>> Server: GBN - envié ACK{pkg_id+1} FINAL por cola a {addr}")
            else:
                writing_queue.put((ack_data, addr))
                print(f">>> Server: envié ACK{pkg_id+1} a {addr}")
            
            expected_pkg_id += 1
        else:
            # Comportamiento diferente según protocolo
            if protocol == STOP_AND_WAIT:
                # Stop-and-Wait: reenviar el último ACK válido (expected_pkg_id)
                writing_queue.put((expected_pkg_id.to_bytes(4, "big"), addr))
                print(f">>> Server: SW - paquete fuera de orden pkg_id={pkg_id}, reenvío ACK{expected_pkg_id}")
            else:
                # Go-Back-N: ACK del último paquete recibido en orden (expected_pkg_id - 1)
                if expected_pkg_id > 0:
                    writing_queue.put(((expected_pkg_id-1).to_bytes(4, "big"), addr))
                    print(f">>> Server: GBN - paquete fuera de orden pkg_id={pkg_id}, reenvío ACK{expected_pkg_id-1}")
                else:
                    # No enviamos ACK si aún no hemos recibido ningún paquete en orden
                    print(f">>> Server: GBN - paquete fuera de orden pkg_id={pkg_id}, no hay paquetes previos para ACK")

        if flag_end == 1:
            print(f">>> Server: paquete final recibido (flag_end=1), pkg_id={pkg_id}")
            
            # Delay solo para Go-Back-N (SW ya envió directo)
            if protocol != STOP_AND_WAIT:
                import time
                time.sleep(0.02)  # 20ms para asegurar envío del ACK final en GBN
                print(f">>> Server: GBN - delay completado para envío final")
            
            print(f">>> Server: finalizando transfer para {addr}")
            work_done = True
            break
    
    # Cerrar archivo al terminar
    arch.archivo.close()
    print(f">>> Server: upload completado para {name} desde {addr}, archivo cerrado")

def manage_client(channel: queue.Queue, addr, sock: socket, writing_queue):
    try:
        print(f">>> Server: iniciando manejo de cliente {addr}")
        conexion_type = channel.get(block=True)
        print(f">>> Server: recibí conexion_type={conexion_type} de {addr}")

        writing_queue.put(((0).to_bytes(4, "big"), addr))
        print(f">>> Server: envié ACK de conexion_type a {addr}")
        
        # Esperar protocol con timeout
        try:
            queue_size = channel.qsize()
            print(f">>> Server: Cola de {addr} tiene {queue_size} paquetes antes de esperar protocol")
            protocol = channel.get(block=True, timeout=2.0)  # Timeout aumentado
            print(f">>> Server: recibí protocol={protocol} de {addr}")
        except queue.Empty:
            queue_size = channel.qsize()
            print(f">>> Server: timeout esperando protocol de {addr}, cola tiene {queue_size} paquetes")
            return

        # Reenviar ACK si el cliente reenvía el mismo paquete
        while protocol == conexion_type:  # entonces el ACK se perdio, reenviamos
            print(f">>> Server: cliente reenvió conexion_type, reenviando ACK a {addr}")
            writing_queue.put(((0).to_bytes(4, "big"), addr))
            try:
                protocol = channel.get(block=True, timeout=2.0)  # Timeout aumentado
            except queue.Empty:
                print(f">>> Server: timeout esperando protocol de {addr}")
                return

        writing_queue.put(((1).to_bytes(4, "big"), addr))
        print(f">>> Server: envié ACK de protocol a {addr}")
        
        # Esperar name con timeout
        try:
            queue_size = channel.qsize()
            print(f">>> Server: Cola de {addr} tiene {queue_size} paquetes antes de esperar name")
            name = channel.get(block=True, timeout=2.0)  # Timeout aumentado
            print(f">>> Server: recibí name={name} de {addr}")
        except queue.Empty:
            queue_size = channel.qsize()
            print(f">>> Server: timeout esperando name de {addr}, cola tiene {queue_size} paquetes")
            return

        # Reenviar ACK si el cliente reenvía el mismo paquete
        while name == protocol:  # entonces el ACK se perdio, reenviamos
            print(f">>> Server: cliente reenvió protocol, reenviando ACK a {addr}")
            writing_queue.put(((1).to_bytes(4, "big"), addr))
            try:
                name = channel.get(block=True, timeout=2.0)  # Timeout aumentado
            except queue.Empty:
                print(f">>> Server: timeout esperando name de {addr}")
                return

        name = name.decode()
        protocol = protocol.decode()
        conexion_type = conexion_type.decode()
        print(f">>> Server: conexion_type={conexion_type}, protocol={protocol}, name={name}, addr={addr}")

        for i in range (1, 11):
            # Enviar ACK del nombre del archivo
            writing_queue.put(((2).to_bytes(4, "big"), addr))
            print(f">>> Server: envié ACK del nombre del archivo: {name}")
        
        if conexion_type == UPLOAD:
            
            
            # Delay para evitar que se mezclen paquetes del handshake con los de datos
            print(f">>> Server: Iniciando delay de 1 segundo para {addr} (upload)")
            import time
            time.sleep(1.0)
            print(f">>> Server: Delay completado para {addr}, iniciando upload_from_client_go_back_n")
            
            if protocol == STOP_AND_WAIT:
                upload_from_client_go_back_n(name, channel, writing_queue, addr, STOP_AND_WAIT, sock)
            elif protocol == GO_BACK_N:
                upload_from_client_go_back_n(name, channel, writing_queue, addr, GO_BACK_N, sock)

        elif conexion_type == DOWNLOAD:
            
            # Delay para evitar que se mezclen paquetes del handshake con los de datos
            print(f">>> Server: Iniciando delay de 1 segundo para {addr} (download)")
            import time
            time.sleep(1.0)
            print(f">>> Server: Delay completado para {addr}, iniciando download_from_client_go_back_n")
            
            if protocol == STOP_AND_WAIT:
                download_from_client_go_back_n(name, writing_queue, addr, WINDOW_SIZE_SW, channel, ACK_TIMEOUT_SW)  # GBN con ventana de 1
            elif protocol == GO_BACK_N:
                download_from_client_go_back_n(name, writing_queue, addr, WINDOW_SIZE_GBN, channel, ACK_TIMEOUT_GBN)
    except Exception as e:
        print(f">>> Server: Error en manage_client: {e}")
        return

def manage_writing(writing_queue: queue.Queue, sock: socket):
    try:
        while True:
            pkg, addr = writing_queue.get(block=True)
            sock.sendto(pkg, addr)
            print(f">>> Server: envié paquete de {len(pkg)} bytes a {addr}")
    except Exception as e:
        print(f">>> Server: Error en manage_writing: {e}")
        return

class Server:
    def __init__(self, udp_ip, udp_port, path):
        self.udp_ip = udp_ip
        self.udp_port = udp_port
        self.clients = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((udp_ip, udp_port))
        print(f"Server bound to {udp_ip}:{udp_port}")
        self.writing_queue = queue.Queue()
        self.writing_thread = None

    def _start_writing_thread(self):
        self.writing_thread = threading.Thread(target=manage_writing, args=(self.writing_queue, self.sock))
        self.writing_thread.start()

    def _listen(self):
        while True:
            try:
                pkg, addr = self.sock.recvfrom(1024)
                print(f">>> Server: recibí paquete de {len(pkg)} bytes de {addr}")
                if addr in self.clients:
                    queue_size = self.clients[addr][0].qsize()
                    print(f">>> Server: Cola de {addr} tiene {queue_size} paquetes antes de agregar")
                    self.clients[addr][0].put(pkg)
                    queue_size_after = self.clients[addr][0].qsize()
                    print(f">>> Server: Cola de {addr} tiene {queue_size_after} paquetes después de agregar")
                else:
                    print(f">>> Server: Cliente nuevo {addr}, iniciando thread")
                    self.start_client(pkg, addr, self.writing_queue)
            except ConnectionResetError:
                print(">>> Server: Conexión reseteada por el cliente")
                continue
            except socket.timeout:
                continue
            except Exception as e:
                print(f">>> Server: Error inesperado: {e}")
                continue

    def start_client(self, msg, addr, writing_queue):
        print(f">>> Server: start_client iniciando para {addr}")
        chan = queue.Queue()
        t = threading.Thread(target=manage_client, args=(chan, addr, self.sock, writing_queue))
        self.clients[addr] = [chan, t]
        chan.put(msg)
        print(f">>> Server: Thread iniciado para {addr}, mensaje inicial: {len(msg)} bytes")
        t.start()


class ServerInterface:
    def __init__(self):
        self.logger = setup_logging('file_transfer_server')
        self.server = None
            
    def start_server(self, args):
        try:
            self.logger = setup_logging('file_transfer_server', args.verbose, args.quiet)
            
            self.logger.info(f"Starting server on {args.host}:{args.port}")
            self.logger.debug(f"Storage path: {args.storage}")
            
            # Crear directorio de almacenamiento si no existe
            os.makedirs(args.storage, exist_ok=True)
            
            # Crear servidor
            self.server = Server(args.host, args.port, args.storage)
            
            self.logger.info("Server started successfully. Press Ctrl+C to stop.")
            self.logger.info("Waiting for connections...")
            
            # Iniciar servidor
            self.server._start_writing_thread()
            self.server._listen()
            
        except KeyboardInterrupt:
            self.logger.info("Server stopped by user")
        except Exception as e:
            self.logger.error(f"Server error: {e}")
            sys.exit(1)
        finally:
            if self.server and self.server.sock:
                self.server.sock.close()


def main():
    if len(sys.argv) < 2:
        print("File Transfer Server")
        print("Usage: python server.py start-server [options]")
        print("Use -h for help with options")
        sys.exit(1)
        
    command = sys.argv[1]
    sys.argv = sys.argv[1:]
    
    interface = ServerInterface()
    
    if command == 'start-server':
        parser = create_server_parser()
        args = parser.parse_args()
        interface.start_server(args)
        
    else:
        print(f"Unknown command: {command}")
        print("Available commands: start-server")
        sys.exit(1)


if __name__ == "__main__":
    main()
