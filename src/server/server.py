import socket
import threading
import queue
import sys
import os
import argparse
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constants import (
    UPLOAD, DOWNLOAD, TUPLA_DIR, UDP_IP, UDP_PORT, PROTOCOLO, STOP_AND_WAIT, GO_BACK_N, WINDOW_SIZE
)
from protocol.archive import ArchiveRecv, ArchiveSender
from protocol.utils import setup_logging, create_server_parser


def upload_from_client(name, channel: queue.Queue, sock: socket, addr):
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
            sock.sendto((seq_expected % 256).to_bytes(1, "big"), addr)  # ACK de 1 bit
            break
        
        if seq_num == seq_expected: 
            arch.archivo.write(data)
            arch.archivo.flush()
            sock.sendto((seq_num % 256).to_bytes(1, "big"), addr)  # ACK de 1 bit
            seq_expected = 1 - seq_expected 
        else: # Duplicado, reenvío ACK del último válido
            sock.sendto(((1 - seq_expected) % 256).to_bytes(1, "big"), addr)  # ACK de 1 bit


def download_from_client_stop_and_wait(name, sock, addr, channel=None):
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
       
        sock.sendto(pkg, addr)
        print(f">>> Server: envió paquete con seq={seq_num} (len={len(pkg)})")

        ack_recv = False
        while not ack_recv:
            try:
                sock.settimeout(0.5)
                ack_data, ack_addr = sock.recvfrom(1024)
                if len(ack_data) == 1:  # ACK de 1 bit
                    ack_num = int.from_bytes(ack_data, "big")
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
        while(len(pkgs_not_ack) < WINDOW_SIZE and not file_finished):
            pkg, pkg_id = arch.next_pkg_go_back_n(seq_num % 2)  # Usar solo 0 o 1 para seq_num
            if pkg is None:
                # Crear paquete END con flag_end = 1
                first_byte = 1  # flag_end = 1 para END
                pkg = first_byte.to_bytes(1, "big") + (0).to_bytes(2, "big") + (0).to_bytes(4, "big")  # data_len = 0, pkg_id = 0
                pkg_id = (0).to_bytes(4, "big")  # pkg_id = 0 para END
                file_finished = True
            sock.sendto(pkg, addr)
            print(f">>> Server: envió paquete con flag_end={pkg[0] & 1}, pkg_id={int.from_bytes(pkg_id, 'big')} (len={len(pkg)})")
            if pkg_id != (0).to_bytes(4, "big"):
                pkgs_not_ack[pkg_id] = pkg
            seq_num += 1
        
        # Fase 2: Esperar ACKs
        print(">>> Server: termine de enviar los paquetes, tengo que esperar ACK")
        sock.settimeout(0.5)
        try:
            pkg, ack_addr = sock.recvfrom(1024)
            print(f">>> Server: recibí el ACK del paquete: {pkg}")
            if len(pkg) == 1:
                ack_num = int.from_bytes(pkg, "big")
                to_remove = []
                for pkg_id in pkgs_not_ack:
                    pkg_id_num = int.from_bytes(pkg_id, 'big')
                    if pkg_id_num % 256 <= ack_num:
                        to_remove.append(pkg_id)
                for pkg_id in to_remove:
                    del pkgs_not_ack[pkg_id]
                
                if file_finished and not pkgs_not_ack:
                    end = True

        except socket.timeout:
            if file_finished and not pkgs_not_ack:
                # Si terminamos el archivo y no hay paquetes sin confirmar, salir
                end = True
            else:
                print(">>> Server: timeout, no recibi ACKs, reenvio los n paquetes")
                for value in pkgs_not_ack.values():
                    sock.sendto(value, addr)
        except ConnectionResetError:
                print(">>> Server: Conexión reseteada durante download")
                return
        except Exception as e:
                print(f">>> Server: Error durante download: {e}")
                return

def upload_from_client_go_back_n(name, channel, sock, addr):
    """
    Recibe archivo del cliente usando Go Back N.
    Funciona como stop and wait desde el lado del servidor.
    """
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
            sock.sendto((seq_expected % 256).to_bytes(1, "big"), addr)  # ACK de 1 bit
            break
        print(f">>> Server: recibí paquete flag_end={flag_end}, pkg_id={pkg_id}, pkg_id_mod={pkg_id % 256}, esperado={seq_expected}, esperado_mod={seq_expected % 256}")
        
        if pkg_id % 256 == seq_expected % 256:
            arch.archivo.write(data)
            arch.archivo.flush()
            ack_value = seq_expected % 256
            sock.sendto(ack_value.to_bytes(1, "big"), addr)
            print(f">>> Server: envié ACK{seq_expected % 256} (valor={ack_value})")
            seq_expected += 1
        else:
            ack_to_send = (seq_expected - 1) % 256
            sock.sendto(ack_to_send.to_bytes(1, "big"), addr)
            print(f">>> Server: paquete fuera de orden, reenvío ACK{ack_to_send}")


def manage_client(channel: queue.Queue, addr, sock: socket):
    try:
        conexion_type = channel.get(block=True)

        sock.sendto((1).to_bytes(1, "big"), addr)  # ACK de conexion_type
        protocol = channel.get(block=True)

        while protocol == conexion_type:  # entonces el ACK se perdio, reenviamos
            sock.sendto((1).to_bytes(1, "big"), addr)
            protocol = channel.get(block=True)

        sock.sendto((1).to_bytes(1, "big"), addr)  # ACK de protocol
        name = channel.get(block=True)

        while name == protocol:  # entonces el ACK se perdio, reenviamos
            sock.sendto((1).to_bytes(1, "big"), addr)
            name = channel.get(block=True)

        name = name.decode()
        protocol = protocol.decode()
        pkg = channel.get(block=True)

        while name == pkg:  # nuevamente, el ACK no llego, tenemos que reenviarlo
            sock.sendto((1).to_bytes(1, "big"), addr)
            pkg = channel.get(block=True)

        print(f">>> Server: conexion_type={conexion_type.decode()}, protocol={protocol}, name={name}")

        if conexion_type == UPLOAD.encode():
            # Enviar ACK del nombre del archivo
            sock.sendto((1).to_bytes(1, "big"), addr)
            print(f">>> Server: envié ACK del nombre del archivo: {name}")
            
            if protocol == STOP_AND_WAIT:
                upload_from_client(name, channel, sock, addr)
            elif protocol == GO_BACK_N:
                upload_from_client_go_back_n(name, channel, sock, addr)

        elif conexion_type == DOWNLOAD.encode():
            # Enviar ACK del nombre del archivo
            sock.sendto((1).to_bytes(1, "big"), addr)
            print(f">>> Server: envié ACK del nombre del archivo: {name}")
            
            if protocol == STOP_AND_WAIT:
                download_from_client_stop_and_wait(name, sock, addr, channel)
            elif protocol == GO_BACK_N:
                download_from_client_go_back_n(name, sock, addr)
    except Exception as e:
        print(f">>> Server: Error en manage_client: {e}")
        return


class Server:
    def __init__(self, udp_ip, udp_port, path):
        self.udp_ip = udp_ip
        self.udp_port = udp_port
        self.clients = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((udp_ip, udp_port))
        print(f"Server bound to {udp_ip}:{udp_port}")

    def _listen(self):
        while True:
            try:
                pkg, addr = self.sock.recvfrom(1024)
                if addr in self.clients:
                    self.clients[addr][0].put(pkg)
                else:
                    self.start_client(pkg, addr)
            except ConnectionResetError:
                print(">>> Server: Conexión reseteada por el cliente")
                continue
            except socket.timeout:
                continue
            except Exception as e:
                print(f">>> Server: Error inesperado: {e}")
                continue

    def start_client(self, msg, addr):
        chan = queue.Queue()
        t = threading.Thread(target=manage_client, args=(chan, addr, self.sock))
        t.start()
        self.clients[addr] = [chan, t]
        chan.put(msg)


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
