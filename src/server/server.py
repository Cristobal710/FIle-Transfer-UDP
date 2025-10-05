import socket
import threading
import queue
import sys
import os
import argparse
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constants import (
    UPLOAD, DOWNLOAD, STOP_AND_WAIT, GO_BACK_N, ACK_TIMEOUT_SW, ACK_TIMEOUT_GBN, WINDOW_SIZE_GBN, WINDOW_SIZE_SW
)
from protocol.archive import ArchiveRecv, ArchiveSender
from protocol.utils import setup_logging, create_server_parser


def upload_from_client(name, channel: queue.Queue, writing_queue: queue.Queue, addr):
    # Usar path absoluto
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "storage", name)
    arch = ArchiveRecv(path)
    seq_expected = 0
    work_done = False
    while not work_done:
        pkg = channel.get(block=True)
        
        seq_num, flag_end, data_len, data = arch.recv_pckg(pkg)
        
        if flag_end == 1:
            work_done = True
            writing_queue.put(((seq_expected % 256).to_bytes(1, "big"), addr))  # ACK de 1 bit
            break
        
        if seq_num == seq_expected: 
            arch.archivo.write(data)
            arch.archivo.flush()
            writing_queue.put(((seq_num % 256).to_bytes(1, "big"), addr))  # ACK de 1 bit
            seq_expected = 1 - seq_expected 
        else: # Duplicado, reenvío ACK del último válido
            writing_queue.put((((1 - seq_expected) % 256).to_bytes(1, "big"), addr))  # ACK de 1 bit


def download_from_client_stop_and_wait(name, writing_queue: queue.Queue, addr, channel, timeout):
    """
    Stop and Wait Download - Servidor envía archivo al cliente
    """
    # Usar path absoluto
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "storage", name)
    print(f">>> Server: buscando archivo en: {path}")
    print(f">>> Server: directorio actual: {os.getcwd()}")
    if not os.path.exists(path):
        print(f">>> Server: archivo no encontrado: {path}")
        return
    print(f">>> Server: archivo encontrado, empezando envío con Stop and Wait...")
    try:
        arch = ArchiveSender(path)
    except Exception as e:
        print(f">>> Server: Error al abrir archivo: {e}")
        return
    
    seq_num = 0
    end = False
    
    while not end:
        pkg = arch.next_pkg(seq_num)
        if pkg is None:
            # Crear paquete END con flag_end = 1
            first_byte = (seq_num << 1) | 1  # flag_end = 1 para END
            pkg = first_byte.to_bytes(1, "big") + (0).to_bytes(2, "big")  # data_len = 0
            end = True
       
        writing_queue.put((pkg, addr))
        print(f">>> Server: envió paquete con seq={seq_num} (len={len(pkg)})")

        ack_recv = False
        while not ack_recv:
            try:
                ack_data = channel.get(block=True, timeout=timeout)
                if len(ack_data) == 1:  # ACK de 1 bit
                    ack_num = int.from_bytes(ack_data, "big")
                    if ack_num == seq_num:
                        print(f">>> Server: recibió ACK{ack_num}")
                        ack_recv = True
                        if not end:
                            seq_num = 1 - seq_num
                    else:
                        print(f">>> Server: ACK incorrecto, esperaba {seq_num}, recibí {ack_num}")
            except queue.Empty:
                print(f">>> Server: timeout esperando ACK{seq_num}, reenvío")
                writing_queue.put((pkg, addr))

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
    
    seq_num = 0
    pkgs_not_ack = {}
    file_finished = False
    end = False
    
    while not end:
        # Fase 1: Enviar paquetes hasta llenar la ventana o terminar el archivo
        while(len(pkgs_not_ack) < window_sz and not file_finished):
            pkg, pkg_id = arch.next_pkg_go_back_n(seq_num)  # Usar seq_num directamente
            if pkg is None:
                # Crear paquete END con flag_end = 1
                first_byte = 1  # flag_end = 1 para END
                pkg = first_byte.to_bytes(1, "big") + (0).to_bytes(2, "big") + (seq_num).to_bytes(4, "big")  # data_len = 0, pkg_id = seq_num
                pkg_id = (seq_num).to_bytes(4, "big")  # pkg_id = seq_num para END
                file_finished = True
                print(f">>> Server: creando paquete END con pkg_id={seq_num}")
            writing_queue.put((pkg, addr))
            print(f">>> Server: envió paquete con flag_end={pkg[0] & 1}, pkg_id={int.from_bytes(pkg_id, 'big')} (len={len(pkg)})")
            
            # Siempre agregar a pkgs_not_ack, incluyendo el paquete END
            pkgs_not_ack[pkg_id] = pkg
            seq_num += 1
        
        # Fase 2: Esperar ACKs
        print(f">>> Server: termine de enviar los paquetes, tengo que esperar ACK. Paquetes sin ACK: {len(pkgs_not_ack)}")
        
        try:
            pkg = channel.get(block=True, timeout=timeout)
            print(f">>> Server: recibí el ACK del paquete: {pkg}")
            if len(pkg) == 4:
                ack_num = int.from_bytes(pkg, "big")
                print(f">>> Server: ACK recibido para paquete {ack_num}")
                
                # Remover todos los paquetes con pkg_id <= ack_num
                to_remove = []
                for pkg_id in pkgs_not_ack:
                    pkg_id_num = int.from_bytes(pkg_id, 'big')
                    if pkg_id_num <= ack_num:
                        to_remove.append(pkg_id)
                        print(f">>> Server: removiendo paquete {pkg_id_num} de la ventana")
                
                for pkg_id in to_remove:
                    del pkgs_not_ack[pkg_id]
                
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

def upload_from_client_go_back_n(name, channel, writing_queue: queue.Queue, addr):
    """
    Recibe archivo del cliente usando Go Back N.
    Funciona como stop and wait desde el lado del servidor.
    """
    print(f">>> Server: upload_from_client_go_back_n iniciado para {name} desde {addr}")
    # Usar path absoluto
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "storage", name)
    arch = ArchiveRecv(path)
    seq_expected = 0
    work_done = False
    
    while not work_done:
        pkg = channel.get(block=True)
        
        flag_end, data_len, pkg_id, data = arch.recv_pckg_go_back_n(pkg)
        
        if flag_end == 1:
            work_done = True
            writing_queue.put((pkg_id.to_bytes(4, "big"), addr))  # ACK de 4 bytes para el pkg_id del paquete END
            print(f">>> Server: envié ACK final {pkg_id} a {addr}")
            break
        print(f">>> Server: recibí paquete flag_end={flag_end}, pkg_id={pkg_id}, esperado={seq_expected}")
        
        if pkg_id == seq_expected:
            arch.archivo.write(data)
            arch.archivo.flush()
            writing_queue.put((seq_expected.to_bytes(4, "big"), addr))
            print(f">>> Server: envié ACK{seq_expected} a {addr}")
            seq_expected += 1
        else:
            writing_queue.put(((seq_expected - 1).to_bytes(4, "big"), addr))
            print(f">>> Server: paquete fuera de orden, reenvío ACK{seq_expected - 1}")


def manage_client(channel: queue.Queue, addr, sock: socket, writing_queue):
    try:
        print(f">>> Server: iniciando manejo de cliente {addr}")
        conexion_type = channel.get(block=True)
        print(f">>> Server: recibí conexion_type={conexion_type} de {addr}")

        writing_queue.put(((1).to_bytes(1, "big"), addr))
        print(f">>> Server: envié ACK de conexion_type a {addr}")
        protocol = channel.get(block=True)
        print(f">>> Server: recibí protocol={protocol} de {addr}")

        while protocol == conexion_type:  # entonces el ACK se perdio, reenviamos
            writing_queue.put(((1).to_bytes(1, "big"), addr))
            protocol = channel.get(block=True)

        writing_queue.put(((1).to_bytes(1, "big"), addr))
        name = channel.get(block=True)

        while name == protocol:  # entonces el ACK se perdio, reenviamos
            writing_queue.put(((1).to_bytes(1, "big"), addr))
            name = channel.get(block=True)

        name = name.decode()
        protocol = protocol.decode()

        print(f">>> Server: conexion_type={conexion_type.decode()}, protocol={protocol}, name={name}, addr={addr}")

        if conexion_type == UPLOAD.encode():
            # Enviar ACK del nombre del archivo
            writing_queue.put(((1).to_bytes(1, "big"), addr))
            print(f">>> Server: envié ACK del nombre del archivo: {name}")
            
            if protocol == STOP_AND_WAIT:
                upload_from_client(name, channel, writing_queue, addr)
            elif protocol == GO_BACK_N:
                upload_from_client_go_back_n(name, channel, writing_queue, addr)

        elif conexion_type == DOWNLOAD.encode():
            # Enviar ACK del nombre del archivo
            writing_queue.put(((1).to_bytes(1, "big"), addr))
            print(f">>> Server: envié ACK del nombre del archivo: {name}")
            if protocol == STOP_AND_WAIT:
                download_from_client_stop_and_wait(name, writing_queue, addr, channel, ACK_TIMEOUT_SW)
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
                    self.clients[addr][0].put(pkg) 
                else:
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
        chan = queue.Queue()
        t = threading.Thread(target=manage_client, args=(chan, addr, self.sock, writing_queue))
        self.clients[addr] = [chan, t]
        chan.put(msg)
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
