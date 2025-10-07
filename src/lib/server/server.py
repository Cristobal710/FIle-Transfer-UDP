import socket
import threading
import queue
import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from lib.constants import (
     UPLOAD, DOWNLOAD, STOP_AND_WAIT, GO_BACK_N, ACK_TIMEOUT_SW, ACK_TIMEOUT_GBN, WINDOW_SIZE_GBN, WINDOW_SIZE_SW
 )
from lib.protocol.protocol import handshake_server, download_from_client, upload_from_client
from lib.protocol.utils import setup_logging, create_server_parser

def manage_client(channel: queue.Queue, addr, sock: socket, writing_queue, verbose=False, quiet=False):

    # ✅ Pasar verbose y quiet
    conexion_type, protocol, name = handshake_server(channel, addr, writing_queue, verbose, quiet)

    for i in range (1, 11):
        # Enviar ACK del nombre del archivo
        writing_queue.put(((2).to_bytes(4, "big"), addr))
        #print(f">>> Server: envié ACK del nombre del archivo: {name}")
    
    if conexion_type == UPLOAD:
        
        # Delay para evitar que se mezclen paquetes del handshake con los de datos
        #print(f">>> Server: Iniciando delay de 1 segundo para {addr} (upload)")
        time.sleep(1.0)
        #print(f">>> Server: Delay completado para {addr}, iniciando upload_from_client_go_back_n")
        
        if protocol == STOP_AND_WAIT:
            upload_from_client(name, channel, writing_queue, addr, STOP_AND_WAIT, sock)
        elif protocol == GO_BACK_N:
            upload_from_client(name, channel, writing_queue, addr, GO_BACK_N, sock)
    elif conexion_type == DOWNLOAD:
        
        # Delay para evitar que se mezclen paquetes del handshake con los de datos
        #print(f">>> Server: Iniciando delay de 1 segundo para {addr} (download)")
        time.sleep(1.0)
        #print(f">>> Server: Delay completado para {addr}, iniciando download_from_client_go_back_n")
        
        if protocol == STOP_AND_WAIT:
            download_from_client(name, writing_queue, addr, WINDOW_SIZE_SW, channel, ACK_TIMEOUT_SW)  # GBN con ventana de 1
        elif protocol == GO_BACK_N:
            download_from_client(name, writing_queue, addr, WINDOW_SIZE_GBN, channel, ACK_TIMEOUT_GBN)
    

def manage_writing(writing_queue: queue.Queue, sock: socket):
    try:
        while True:
            pkg, addr = writing_queue.get(block=True)
            sock.sendto(pkg, addr)
            #print(f">>> Server: envié paquete de {len(pkg)} bytes a {addr}")
    except Exception as e:
        #print(f">>> Server: Error en manage_writing: {e}")
        return




class Server:
    def __init__(self, udp_ip, udp_port, path, verbose=False, quiet=False):
        self.udp_ip = udp_ip
        self.udp_port = udp_port
        self.verbose = verbose  
        self.quiet = quiet      
        self.clients = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((udp_ip, udp_port))
        #print(f"Server bound to {udp_ip}:{udp_port}")
        self.writing_queue = queue.Queue()
        self.writing_thread = None

    def _start_writing_thread(self):
        self.writing_thread = threading.Thread(target=manage_writing, args=(self.writing_queue, self.sock))
        self.writing_thread.start()

    def _listen(self):
        while True:
            try:
                pkg, addr = self.sock.recvfrom(1024)
                #print(f">>> Server: recibí paquete de {len(pkg)} bytes de {addr}")
                if addr in self.clients:
                    queue_size = self.clients[addr][0].qsize()
                    #print(f">>> Server: Cola de {addr} tiene {queue_size} paquetes antes de agregar")
                    self.clients[addr][0].put(pkg)
                    queue_size_after = self.clients[addr][0].qsize()
                    #print(f">>> Server: Cola de {addr} tiene {queue_size_after} paquetes después de agregar")
                else:
                    #print(f">>> Server: Cliente nuevo {addr}, iniciando thread")
                    self.start_client(pkg, addr, self.writing_queue)
            except ConnectionResetError:
                #print(">>> Server: Conexión reseteada por el cliente")
                continue
            except socket.timeout:
                continue
            except Exception as e:
                #print(f">>> Server: Error inesperado: {e}")
                continue

    def start_client(self, msg, addr, writing_queue):
        #print(f">>> Server: start_client iniciando para {addr}")
        chan = queue.Queue()
        t = threading.Thread(target=manage_client, args=(chan, addr, self.sock, writing_queue, self.verbose, self.quiet))
        self.clients[addr] = [chan, t]
        chan.put(msg)
        #print(f">>> Server: Thread iniciado para {addr}, mensaje inicial: {len(msg)} bytes")
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
            self.server = Server(args.host, args.port, args.storage, args.verbose, args.quiet)
            
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
    interactive_logger = setup_logging('file_transfer_server.interactive')
    if len(sys.argv) < 2:
        interactive_logger.info("File Transfer Server")
        interactive_logger.info("Uso: python server.py start-server [options]")
        interactive_logger.info("Presione -h para ayuda en cada comando")
        sys.exit(1)
        
    command = sys.argv[1]
    sys.argv = sys.argv[1:]
    
    interface = ServerInterface()
    
    if command == 'start-server':
        parser = create_server_parser()
        args = parser.parse_args()
        interface.start_server(args)
        
    else:
        interactive_logger.warning(f"Comando desconocido: {command}")
        interactive_logger.info("Comandos validos: upload, download")
        sys.exit(1)


if __name__ == "__main__":
    main()
