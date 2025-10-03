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


def upload_from_client(name, channel: queue.Queue, sock: socket, addr, server_instance):
    # Usar path absoluto
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "storage", name)
    arch = ArchiveRecv(path)
    seq_expected = 0
    work_done = False
    print(f">>> Server [{addr}]: empezando recepción de archivo: {name}")
    
    while not work_done:
        pkg_data, pkg_addr = channel.get(block=True)
        pkg = pkg_data
        
        seq_num, flag_end, data_len, data = arch.recv_pckg(pkg)
        
        if flag_end == 1:
            work_done = True
            server_instance.send_ack((seq_expected % 256).to_bytes(1, "big"), addr)  # ACK de 1 bit
            print(f">>> Server [{addr}]: transferencia completada")
            break
        
        if seq_num == seq_expected: 
            arch.archivo.write(data)
            arch.archivo.flush()
            server_instance.send_ack((seq_num % 256).to_bytes(1, "big"), addr)  # ACK de 1 bit
            print(f">>> Server [{addr}]: envió ACK{seq_num}")
            seq_expected = 1 - seq_expected 
        else: # Duplicado, reenvío ACK del último válido
            server_instance.send_ack(((1 - seq_expected) % 256).to_bytes(1, "big"), addr)  # ACK de 1 bit
            print(f">>> Server [{addr}]: paquete duplicado, reenvío ACK{1 - seq_expected}")


def download_from_client_stop_and_wait(name, sock, addr, channel):
    """
    Stop and Wait Download - Servidor envía archivo al cliente
    """
    # Usar path absoluto
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "storage", name)
    print(f">>> Server [{addr}]: buscando archivo en: {path}")
    if not os.path.exists(path):
        print(f">>> Server [{addr}]: archivo no encontrado: {path}")
        return
    print(f">>> Server [{addr}]: archivo encontrado, empezando envío con Stop and Wait...")
    try:
        arch = ArchiveSender(path)
    except Exception as e:
        print(f">>> Server [{addr}]: Error al abrir archivo: {e}")
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
        print(f">>> Server [{addr}]: envió paquete con seq={seq_num} (len={len(pkg)})")

        ack_recv = False
        while not ack_recv:
            try:
                # Esperar ACK desde la cola con timeout
                ack_data, ack_addr = channel.get(block=True, timeout=0.5)
                # Verificar que el ACK viene del cliente correcto
                if ack_addr == addr and len(ack_data) == 1:  # ACK de 1 bit
                    ack_num = int.from_bytes(ack_data, "big")
                    if ack_num == seq_num:
                        print(f">>> Server [{addr}]: recibió ACK{ack_num}")
                        ack_recv = True
                        if not end:
                            seq_num = 1 - seq_num
                    else:
                        print(f">>> Server [{addr}]: ACK incorrecto, esperaba {seq_num}, recibí {ack_num}")
                else:
                    print(f">>> Server [{addr}]: ACK de cliente incorrecto o formato inválido")
            except queue.Empty:
                print(f">>> Server [{addr}]: timeout esperando ACK{seq_num}, reenvío")
                sock.sendto(pkg, addr)
            except Exception as e:
                print(f">>> Server [{addr}]: Error esperando ACK: {e}")
                break



def download_from_client_go_back_n(name, sock, addr, channel):
    """
    Envía archivo al cliente usando Go Back N.
    Utiliza una ventana deslizante para enviar n paquetes y luego esperar ACKs.
    """
    # Usar path absoluto
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "storage", name)
    if not os.path.exists(path):
        print(f">>> Server [{addr}]: archivo no encontrado: {path}")
        return
    print(f">>> Server [{addr}]: archivo encontrado, empezando envío con Go Back N...")
    arch = ArchiveSender(path)
    
    seq_num = 0
    pkgs_not_ack = {}
    file_finished = False
    end = False
    
    while not end:
        # Fase 1: Enviar paquetes hasta llenar la ventana o terminar el archivo
        while(len(pkgs_not_ack) < WINDOW_SIZE and not file_finished):
            pkg, pkg_id = arch.next_pkg_go_back_n(seq_num)  # Usar seq_num directamente
            if pkg is None:
                # Crear paquete END con flag_end = 1
                first_byte = 1  # flag_end = 1 para END
                pkg = first_byte.to_bytes(1, "big") + (0).to_bytes(2, "big") + (seq_num).to_bytes(4, "big")  # data_len = 0, pkg_id = seq_num
                pkg_id = (seq_num).to_bytes(4, "big")  # pkg_id = seq_num para END
                file_finished = True
            sock.sendto(pkg, addr)
            print(f">>> Server [{addr}]: envió paquete con flag_end={pkg[0] & 1}, pkg_id={int.from_bytes(pkg_id, 'big')} (len={len(pkg)})")
            if pkg_id != (0).to_bytes(4, "big"):
                pkgs_not_ack[pkg_id] = pkg
            seq_num += 1
        
        # Fase 2: Esperar ACKs desde la cola
        print(f">>> Server [{addr}]: termine de enviar los paquetes, tengo que esperar ACK")
        try:
            ack_data, ack_addr = channel.get(block=True, timeout=0.5)
            # Verificar que el ACK viene del cliente correcto
            if ack_addr == addr:
                print(f">>> Server [{addr}]: recibí el ACK del paquete: {ack_data}")
                if len(ack_data) == 4:
                    ack_num = int.from_bytes(ack_data, "big")
                to_remove = []
                for pkg_id in pkgs_not_ack:
                    pkg_id_num = int.from_bytes(pkg_id, 'big')
                    if pkg_id_num <= ack_num:
                        to_remove.append(pkg_id)
                for pkg_id in to_remove:
                    del pkgs_not_ack[pkg_id]
                
                if file_finished and not pkgs_not_ack:
                    end = True
            else:
                print(f">>> Server [{addr}]: ACK de cliente incorrecto, ignorando")

        except queue.Empty:
            if file_finished and not pkgs_not_ack:
                # Si terminamos el archivo y no hay paquetes sin confirmar, salir
                end = True
            else:
                print(f">>> Server [{addr}]: timeout, no recibi ACKs, reenvio los n paquetes")
                for value in pkgs_not_ack.values():
                    sock.sendto(value, addr)
        except ConnectionResetError:
                print(f">>> Server [{addr}]: Conexión reseteada durante download")
                return
        except Exception as e:
                print(f">>> Server [{addr}]: Error durante download: {e}")
                return

def upload_from_client_go_back_n(name, channel, sock, addr, server_instance):
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
    print(f">>> Server [{addr}]: empezando recepción de archivo con Go Back N: {name}")
    
    while not work_done:
        pkg_data, pkg_addr = channel.get(block=True)
        pkg = pkg_data
        
        flag_end, data_len, pkg_id, data = arch.recv_pckg_go_back_n(pkg)
        
        if flag_end == 1:
            work_done = True
            server_instance.send_ack(seq_expected.to_bytes(4, "big"), addr)  # ACK de 4 bytes
            print(f">>> Server [{addr}]: transferencia completada")
            break
        print(f">>> Server [{addr}]: recibí paquete flag_end={flag_end}, pkg_id={pkg_id}, esperado={seq_expected}")
        
        if pkg_id == seq_expected:
            arch.archivo.write(data)
            arch.archivo.flush()
            server_instance.send_ack(seq_expected.to_bytes(4, "big"), addr)
            print(f">>> Server [{addr}]: envié ACK{seq_expected}")
            seq_expected += 1
        else:
            server_instance.send_ack((seq_expected - 1).to_bytes(4, "big"), addr)
            print(f">>> Server [{addr}]: paquete fuera de orden, reenvío ACK{seq_expected - 1}")


def manage_client_with_handshake(channel: queue.Queue, addr, sock: socket, server_instance, conexion_type, protocol, name):
    """Maneja un cliente con los datos del handshake ya recibidos"""
    try:
        print(f">>> Server [{addr}]: iniciando manejo de cliente con handshake completado")
        
        # Decodificar los datos del handshake
        conexion_type_str = conexion_type.decode()
        protocol_str = protocol.decode()
        name_str = name.decode()

        print(f">>> Server [{addr}]: conexion_type={conexion_type_str}, protocol={protocol_str}, name={name_str}")

        if conexion_type == UPLOAD.encode():
            print(f">>> Server [{addr}]: iniciando upload de {name_str}")
            
            if protocol_str == STOP_AND_WAIT:
                upload_from_client(name_str, channel, sock, addr, server_instance)
            elif protocol_str == GO_BACK_N:
                upload_from_client_go_back_n(name_str, channel, sock, addr, server_instance)

        elif conexion_type == DOWNLOAD.encode():
            print(f">>> Server [{addr}]: iniciando download de {name_str}")
            
            if protocol_str == STOP_AND_WAIT:
                download_from_client_stop_and_wait(name_str, sock, addr, channel)
            elif protocol_str == GO_BACK_N:
                download_from_client_go_back_n(name_str, sock, addr, channel)
                
        print(f">>> Server [{addr}]: transferencia completada")
        
    except Exception as e:
        print(f">>> Server [{addr}]: Error en manage_client_with_handshake: {e}")
    finally:
        # Marcar cliente como inactivo
        with server_instance.lock:
            if addr in server_instance.clients:
                server_instance.clients[addr]['active'] = False
        print(f">>> Server [{addr}]: cliente finalizado")

def manage_client(channel: queue.Queue, addr, sock: socket, server_instance):
    """Maneja un cliente individual usando su cola específica (versión legacy)"""
    try:
        print(f">>> Server [{addr}]: iniciando manejo de cliente")
        
        # Obtener tipo de conexión
        pkg_data, pkg_addr = channel.get(block=True)
        conexion_type = pkg_data
        sock.sendto((1).to_bytes(1, "big"), addr)  # ACK de conexion_type
        print(f">>> Server [{addr}]: recibió tipo de conexión: {conexion_type.decode()}")

        # Obtener protocolo
        pkg_data, pkg_addr = channel.get(block=True)
        protocol = pkg_data
        
        # Verificar si el protocolo es igual al tipo de conexión (ACK perdido)
        while protocol == conexion_type:
            print(f">>> Server [{addr}]: ACK perdido, reenviando")
            sock.sendto((1).to_bytes(1, "big"), addr)
            pkg_data, pkg_addr = channel.get(block=True)
            protocol = pkg_data

        sock.sendto((1).to_bytes(1, "big"), addr)  # ACK de protocol
        print(f">>> Server [{addr}]: recibió protocolo: {protocol.decode()}")

        # Obtener nombre del archivo
        pkg_data, pkg_addr = channel.get(block=True)
        name = pkg_data
        
        # Verificar si el nombre es igual al protocolo (ACK perdido)
        while name == protocol:
            print(f">>> Server [{addr}]: ACK perdido, reenviando")
            sock.sendto((1).to_bytes(1, "big"), addr)
            pkg_data, pkg_addr = channel.get(block=True)
            name = pkg_data

        name = name.decode()
        protocol = protocol.decode()

        print(f">>> Server [{addr}]: conexion_type={conexion_type.decode()}, protocol={protocol}, name={name}")

        if conexion_type == UPLOAD.encode():
            # Enviar ACK del nombre del archivo
            sock.sendto((1).to_bytes(1, "big"), addr)
            print(f">>> Server [{addr}]: envié ACK del nombre del archivo: {name}")
            
            if protocol == STOP_AND_WAIT:
                upload_from_client(name, channel, sock, addr)
            elif protocol == GO_BACK_N:
                upload_from_client_go_back_n(name, channel, sock, addr)

        elif conexion_type == DOWNLOAD.encode():
            # Enviar ACK del nombre del archivo
            sock.sendto((1).to_bytes(1, "big"), addr)
            print(f">>> Server [{addr}]: envié ACK del nombre del archivo: {name}")
            
            if protocol == STOP_AND_WAIT:
                download_from_client_stop_and_wait(name, sock, addr, channel)
            elif protocol == GO_BACK_N:
                download_from_client_go_back_n(name, sock, addr, channel)
                
        print(f">>> Server [{addr}]: transferencia completada")
        
    except Exception as e:
        print(f">>> Server [{addr}]: Error en manage_client: {e}")
    finally:
        # Marcar cliente como inactivo
        with server_instance.lock:
            if addr in server_instance.clients:
                server_instance.clients[addr]['active'] = False
        print(f">>> Server [{addr}]: cliente finalizado")


class Server:
    def __init__(self, udp_ip, udp_port, path):
        self.udp_ip = udp_ip
        self.udp_port = udp_port
        self.clients = {}  # {addr: {'queue': queue, 'thread': thread, 'active': bool}}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((udp_ip, udp_port))
        self.sock.settimeout(0.1)  # Timeout corto para permitir limpieza
        self.lock = threading.Lock()  # Lock para proteger acceso a self.clients
        print(f"Server bound to {udp_ip}:{udp_port}")

    def _listen(self):
        """
        Dispatcher centralizado que recibe todos los paquetes y los enruta
        a las colas correctas de cada cliente
        """
        while True:
            try:
                pkg, addr = self.sock.recvfrom(1024)
                print(f">>> Server: recibió paquete de {addr} ({len(pkg)} bytes)")
                
                with self.lock:
                    if addr in self.clients and self.clients[addr]['active']:
                        # Cliente existente - enrutar a su cola
                        try:
                            self.clients[addr]['queue'].put_nowait((pkg, addr))
                            print(f">>> Server: paquete enrutado a cola de {addr}")
                        except queue.Full:
                            print(f">>> Server: cola llena para {addr}, descartando paquete")
                    else:
                        # Nuevo cliente - manejar handshake directamente
                        print(f">>> Server: nuevo cliente {addr}, iniciando handshake")
                        self._handle_handshake(pkg, addr)
                        
            except socket.timeout:
                # Timeout normal - continuar
                continue
            except ConnectionResetError:
                print(">>> Server: Conexión reseteada por el cliente")
                continue
            except Exception as e:
                print(f">>> Server: Error inesperado: {e}")
                continue

    def _handle_handshake(self, first_msg, addr):
        """Maneja el handshake inicial directamente sin dispatcher"""
        try:
            print(f">>> Server [{addr}]: iniciando handshake")
            
            # Paso 1: Recibir tipo de conexión
            conexion_type = first_msg
            self.sock.sendto((1).to_bytes(1, "big"), addr)  # ACK
            print(f">>> Server [{addr}]: recibió tipo: {conexion_type.decode()}")
            
            # Paso 2: Recibir protocolo
            pkg, _ = self.sock.recvfrom(1024)
            protocol = pkg
            self.sock.sendto((1).to_bytes(1, "big"), addr)  # ACK
            print(f">>> Server [{addr}]: recibió protocolo: {protocol.decode()}")
            
            # Paso 3: Recibir nombre del archivo
            pkg, _ = self.sock.recvfrom(1024)
            name = pkg
            self.sock.sendto((1).to_bytes(1, "big"), addr)  # ACK
            print(f">>> Server [{addr}]: recibió nombre: {name.decode()}")
            
            # Ahora crear el cliente y pasarle los datos del handshake
            self.start_client_with_handshake(conexion_type, protocol, name, addr)
            
        except Exception as e:
            print(f">>> Server [{addr}]: Error en handshake: {e}")

    def send_ack(self, ack_data, addr):
        """Envía un ACK directamente al cliente"""
        try:
            self.sock.sendto(ack_data, addr)
            print(f">>> Server [{addr}]: envió ACK: {ack_data}")
        except Exception as e:
            print(f">>> Server [{addr}]: Error enviando ACK: {e}")

    def start_client_with_handshake(self, conexion_type, protocol, name, addr):
        """Inicia un cliente con los datos del handshake ya recibidos"""
        with self.lock:
            # Si ya existe, limpiar primero
            if addr in self.clients:
                self._cleanup_client(addr)
            
            # Crear nueva cola y thread
            chan = queue.Queue(maxsize=100)
            t = threading.Thread(target=manage_client_with_handshake, 
                               args=(chan, addr, self.sock, self, conexion_type, protocol, name))
            t.daemon = True
            t.start()
            
            self.clients[addr] = {
                'queue': chan, 
                'thread': t, 
                'active': True
            }
            
            print(f">>> Server: cliente {addr} iniciado con handshake completado")

    def start_client(self, msg, addr):
        """Inicia un nuevo cliente con su cola y thread dedicados"""
        with self.lock:
            # Si ya existe, limpiar primero
            if addr in self.clients:
                self._cleanup_client(addr)
            
            # Crear nueva cola y thread
            chan = queue.Queue(maxsize=100)  # Limitar tamaño de cola
            t = threading.Thread(target=manage_client, args=(chan, addr, self.sock, self))
            t.daemon = True  # Thread daemon para que termine con el programa
            t.start()
            
            self.clients[addr] = {
                'queue': chan, 
                'thread': t, 
                'active': True
            }
            
            # Enviar mensaje inicial
            try:
                chan.put_nowait((msg, addr))
                print(f">>> Server: cliente {addr} iniciado correctamente")
            except queue.Full:
                print(f">>> Server: error - cola llena al iniciar cliente {addr}")

    def _cleanup_client(self, addr):
        """Limpia un cliente específico"""
        if addr in self.clients:
            client_info = self.clients[addr]
            client_info['active'] = False
            
            # Limpiar cola
            try:
                while not client_info['queue'].empty():
                    client_info['queue'].get_nowait()
            except queue.Empty:
                pass
            
            # El thread se cerrará automáticamente cuando termine
            del self.clients[addr]
            print(f">>> Server: cliente {addr} limpiado")


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
