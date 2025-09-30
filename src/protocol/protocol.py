import socket
import queue
from protocol.archive import ArchiveSender, ArchiveRecv
from constants import END, ACK_TIMEOUT, TUPLA_DIR_ENVIO

class PacketReader:
    """
    Clase que abstrae la lectura de paquetes desde socket o queue
    Permite usar las mismas funciones de protocolo en cliente y servidor
    """
    
    def __init__(self, source, addr=None):
        """
        Inicializa el lector de paquetes
        
        Args:
            source: Socket o Queue para leer paquetes
            addr: Dirección para envío (solo para socket)
        """
        self.source = source
        self.addr = addr
        self.is_socket = isinstance(source, socket.socket)
        self.is_queue = isinstance(source, queue.Queue)
    
    def read_packet(self, timeout=None):
        """
        Lee un paquete desde la fuente
        
        Args:
            timeout: Timeout para la lectura (solo para socket)
            
        Returns:
            tuple: (packet_data, sender_addr) o (packet_data, None) para queue
        """
        if self.is_socket:
            if timeout:
                self.source.settimeout(timeout)
            try:
                packet, addr = self.source.recvfrom(2048)  # Buffer más grande para paquetes grandes
                return packet, addr
            except socket.timeout:
                raise socket.timeout("Timeout reading packet")
        elif self.is_queue:
            try:
                if timeout:
                    packet = self.source.get(block=True, timeout=timeout)
                else:
                    packet = self.source.get(block=True)
                return packet, self.addr
            except queue.Empty:
                raise socket.timeout("Timeout reading packet")
    
    def send_packet(self, packet, dest_addr=None):
        """
        Envía un paquete
        
        Args:
            packet: Datos del paquete
            dest_addr: Dirección de destino (solo para socket)
        """
        if self.is_socket:
            self.source.sendto(packet, dest_addr or self.addr)
        elif self.is_queue:
            # Para queue, necesitamos acceso al socket del servidor
            # Esto se maneja en el servidor directamente
            pass

"""
Handshake
1. Send type of conexion to server (UPLOAD or DOWNLOAD)
2. Server sends ACK
3. Send file name to server
4. Server sends ACK
"""
def handshake(sock: socket, name: str, type: str):
    stop_and_wait(sock, type.encode(), TUPLA_DIR_ENVIO) # send type of conexion to server
    stop_and_wait(sock, name.encode(), TUPLA_DIR_ENVIO) # send file name to server
  
"""
Stop and Wait - Lado que ENVÍA (Upload desde cliente o Download desde servidor)
1. Send pkg
2. Recibe ACK
3. If ACK is not received, resend pkg
4. Repeat until end of file
"""
def send_stop_and_wait(sock: socket, arch: ArchiveSender, dest_addr, end=False):
    seq_num = 0
    packet_count = 0
    print(f"send_stop_and_wait: empezando con seq_num={seq_num}")
    
    while True:
        pkg = arch.next_pkg(seq_num)
        packet_count += 1
        print(f"send_stop_and_wait: paquete #{packet_count}, seq_num={seq_num}, pkg_len={len(pkg) if pkg else 0}")
        
        if pkg is None:
            pkg = END.encode()
            print("send_stop_and_wait: enviando END")
        
        # Enviar paquete y esperar ACK
        sock.sendto(pkg, dest_addr)
        ack_received = False
        
        while not ack_received:
            try:
                sock.settimeout(0.3)  # Timeout balanceado para localhost
                ack_data, addr = sock.recvfrom(2048)
                if ack_data.startswith(b"ACK"):
                    ack_received = True
                    print(f"ACK recibido: {ack_data.decode()}")
                else:
                    print(f"Paquete no es ACK: {ack_data}")
            except socket.timeout:
                print("Timeout, reenviando paquete")
                sock.sendto(pkg, dest_addr)
        
        # Si era el paquete END, terminar
        if pkg == END.encode():
            break
            
        # Alternar seq_num para el siguiente paquete ANTES de continuar
        seq_num = 1 - seq_num

"""
Stop and Wait - Lado que RECIBE (Download en cliente o Upload en servidor)
1. Recibe pkg
2. Envía ACK
3. Si es paquete duplicado, reenvía ACK del último válido
4. Repeat until end of file
"""
def receive_stop_and_wait(sock: socket, arch: ArchiveRecv, sender_addr, end=False):
    seq_expected = 0
    work_done = False
    packet_count = 0

    while not work_done:
        try:
            sock.settimeout(1.0)  # Timeout de 1 segundo
            pkg, addr = sock.recvfrom(2048)  # Buffer más grande para paquetes grandes
        except socket.timeout:
            print(">>> Timeout esperando paquetes del servidor")
            break

        if pkg == END.encode():
            print(f">>> Transferencia finalizada. Total paquetes recibidos: {packet_count}")
            work_done = True
            sock.sendto(f"ACK{seq_expected}".encode(), addr)
            arch.archivo.close()
            break

        packet_count += 1
        seq_num, data_len, data = arch.recv_pckg(pkg)
        print(f">>> Paquete #{packet_count}: seq={seq_num}, esperado={seq_expected}, len={data_len}")

        if seq_num == seq_expected:
            # Enviar ACK INMEDIATAMENTE (antes de escribir)
            sock.sendto(f"ACK{seq_num}".encode(), addr)
            print(f">>> Mando ACK{seq_num}")
            
            # Escribir datos después del ACK
            arch.archivo.write(data)
            # Flush cada 10 paquetes para mejor rendimiento
            if packet_count % 10 == 0:
                arch.archivo.flush()
            
            seq_expected = 1 - seq_expected
        else:
            sock.sendto(f"ACK{1 - seq_expected}".encode(), addr)
            print(f">>> Paquete duplicado, reenvío ACK{1 - seq_expected}")

"""
Stop and Wait simple packagesender
1. Send msg
2. Server sends ACK
3. If ACK is not received, resend msg
4. Repeat until ack is received
"""
def stop_and_wait(sock: socket, msg, addr):
    sock.sendto(msg, addr)
    ack_recv = False
    while not ack_recv:
        sock.settimeout(0.1)  # Timeout corto para localhost
        try:
            pkg, addr = sock.recvfrom(2048)  # Buffer más grande para paquetes grandes
            # Verificar que sea un ACK válido
            if pkg.startswith(b"ACK"):
                ack_recv = True
                print(f"ACK recibido: {pkg.decode()}")
            else:
                print(f"Paquete no es ACK: {pkg}")
        except socket.timeout:
            print("timeout, no recibi ACK")
            sock.sendto(msg, addr)

"""
Go Back N - Lado que ENVÍA (Upload desde cliente o Download desde servidor)
- send_base: primer paquete no confirmado
- nextseqnum: próximo número de secuencia a enviar
- Ventana deslizante de tamaño N
"""
def send_go_back_n(sock: socket, arch: ArchiveSender, dest_addr, end=False, window_sz=4):
    import time
    
    send_base = 0
    nextseqnum = 0
    packets = {}  # {seq_num: (packet, pkg_id)}
    timer_started = False
    timer_start_time = 0

    while True:
        # Enviar paquetes si hay espacio en la ventana
        if nextseqnum < send_base + window_sz and not end:
            pkg, pkg_id = arch.next_pkg_go_back_n(nextseqnum % 2)  # Alternar 0/1
            if pkg is None:
                pkg = END.encode()
                pkg_id = b"END"
                end = True

            packets[nextseqnum] = (pkg, pkg_id)
            sock.sendto(pkg, dest_addr)
            print(f"Enviado paquete {nextseqnum}, pkg_id={int.from_bytes(pkg_id, 'big') if pkg_id != b'END' else 'END'}")
            
            # Iniciar timer si es el primer paquete
            if not timer_started:
                timer_started = True
                timer_start_time = time.time()
            
            nextseqnum += 1
            
            # Sin pausa para máximo rendimiento
        
        # Si no hay más datos que enviar, esperar confirmaciones
        if end and send_base < nextseqnum:
            # Esperar a que se confirmen todos los paquetes antes de terminar
            while send_base < nextseqnum:
                try:
                    sock.settimeout(0.1)
                    ack_data, addr = sock.recvfrom(2048)
                    ack_num = int.from_bytes(ack_data, "big")
                    print(f"Recibí ACK {ack_num}")
                    
                    if ack_num > send_base:
                        send_base = ack_num
                        print(f"send_base actualizado a {send_base}")
                    elif ack_num == send_base:
                        print(f"ACK duplicado {ack_num}, ignorando")
                        
                except socket.timeout:
                    # Reenviar paquetes no confirmados
                    for i in range(send_base, nextseqnum):
                        if i in packets:
                            pkg, pkg_id = packets[i]
                            sock.sendto(pkg, dest_addr)
                            print(f"Reenviado paquete {i}")
                            time.sleep(0.001)
            break
        
        # Procesar ACKs continuamente
        try:
            sock.settimeout(0.05)  # Timeout muy corto para localhost
            ack_data, addr = sock.recvfrom(2048)
            ack_num = int.from_bytes(ack_data, "big")
            print(f"Recibí ACK {ack_num}")
            
            # En Go Back N, el ACK indica el próximo paquete esperado
            if ack_num > send_base:
                send_base = ack_num
                print(f"send_base actualizado a {send_base}")
                
                if send_base == nextseqnum:
                    # Todos los paquetes confirmados
                    timer_started = False
                else:
                    # Reiniciar timer
                    timer_started = True
                    timer_start_time = time.time()
            elif ack_num == send_base:
                # ACK duplicado, ignorar
                print(f"ACK duplicado {ack_num}, ignorando")

        except socket.timeout:
            pass  # No hay ACK, continuar
        
        # Verificar timeout solo si hay paquetes no confirmados
        if timer_started and send_base < nextseqnum and time.time() - timer_start_time > ACK_TIMEOUT:
            print(f"Timeout! Reenviando desde {send_base} hasta {nextseqnum-1}")
            timer_started = True
            timer_start_time = time.time()
            
            # Reenviar solo los paquetes no confirmados
            for i in range(send_base, nextseqnum):
                if i in packets:
                    pkg, pkg_id = packets[i]
                    sock.sendto(pkg, dest_addr)
                    print(f"Reenviado paquete {i}")
                    # Pausa mínima entre reenvíos
                    time.sleep(0.001)
        
        # Si todos los paquetes están confirmados y no hay más datos, terminar
        if send_base == nextseqnum and end:
            break

"""
Go Back N - Lado que RECIBE (Download en cliente o Upload en servidor)
- Solo acepta paquetes en orden
- Descarta paquetes fuera de orden
- Envía ACK del último paquete válido recibido
"""
def receive_go_back_n(sock: socket, arch: ArchiveRecv, sender_addr, end=False):
    expected_seq = 0
    work_done = False
    
    while not work_done:
        pkg, addr = sock.recvfrom(2048)  # Buffer más grande para paquetes grandes
        
        if pkg == END.encode():
            print(">>> Transferencia finalizada.")
            work_done = True
            sock.sendto(expected_seq.to_bytes(4, "big"), addr)
            arch.archivo.close()
            break
        
        # Parsear paquete Go Back N
        seq_num, data_len, pkg_id, data = arch.recv_pckg_go_back_n(pkg)
        print(f">>> Recibí seq={seq_num}, esperado={expected_seq}, pkg_id={pkg_id}, len={data_len}")
        
        if pkg_id == expected_seq:
            # Paquete correcto: escribir datos y enviar ACK
            arch.archivo.write(data)
            arch.archivo.flush()
            sock.sendto(expected_seq.to_bytes(4, "big"), addr)
            print(f">>> Enviando ACK{expected_seq}")
            expected_seq += 1
        else:
            # Paquete fuera de orden: reenviar ACK del último válido
            # Si expected_seq es 0, enviar ACK 0 (no -1)
            ack_to_send = max(0, expected_seq - 1)
            sock.sendto(ack_to_send.to_bytes(4, "big"), addr)
            print(f">>> Paquete fuera de orden, reenviando ACK{ack_to_send}")

# =============================================================================
# FUNCIONES UNIFICADAS DE UPLOAD Y DOWNLOAD
# =============================================================================

def upload_file(sock, arch: ArchiveSender, dest_addr, protocolo="SW", window_sz=4):
    """
    Función unificada para UPLOAD de archivos
    
    Args:
        sock: Socket UDP
        arch: Objeto ArchiveSender
        dest_addr: Dirección de destino
        protocolo: "SW" o "GBN"
        window_sz: Tamaño de ventana para GBN
    """
    if protocolo == "SW":
        send_stop_and_wait(sock, arch, dest_addr)
    else:  # GBN
        send_go_back_n(sock, arch, dest_addr, window_sz=window_sz)

def download_file(reader: PacketReader, arch: ArchiveRecv, sender_addr, protocolo="SW"):
    """
    Función unificada para DOWNLOAD de archivos
    
    Args:
        reader: PacketReader (socket o queue)
        arch: Objeto ArchiveRecv
        sender_addr: Dirección del remitente
        protocolo: "SW" o "GBN"
    """
    if protocolo == "SW":
        receive_stop_and_wait_unified(reader, arch, sender_addr)
    else:  # GBN
        receive_go_back_n_unified(reader, arch, sender_addr)

def receive_stop_and_wait_unified(reader: PacketReader, arch: ArchiveRecv, sender_addr):
    """
    Stop and Wait - Lado que RECIBE (unificado para socket/queue)
    """
    seq_expected = 0
    work_done = False
    packet_count = 0

    while not work_done:
        try:
            pkg, addr = reader.read_packet()
        except socket.timeout:
            continue

        if pkg == END.encode():
            print(f">>> Transferencia finalizada. Total paquetes recibidos: {packet_count}")
            work_done = True
            reader.send_packet(f"ACK{seq_expected}".encode(), sender_addr)
            arch.archivo.close()
            break

        packet_count += 1
        seq_num, data_len, data = arch.recv_pckg(pkg)
        print(f">>> Paquete #{packet_count}: seq={seq_num}, esperado={seq_expected}, len={data_len}")

        if seq_num == seq_expected:
            arch.archivo.write(data)
            arch.archivo.flush()
            reader.send_packet(f"ACK{seq_num}".encode(), sender_addr)
            print(f">>> Mando ACK{seq_num}")
            seq_expected = 1 - seq_expected
        else:
            reader.send_packet(f"ACK{1 - seq_expected}".encode(), sender_addr)
            print(f">>> Paquete duplicado, reenvío ACK{1 - seq_expected}")

def receive_go_back_n_unified(reader: PacketReader, arch: ArchiveRecv, sender_addr):
    """
    Go Back N - Lado que RECIBE (unificado para socket/queue)
    """
    expected_seq = 0
    work_done = False
    
    while not work_done:
        try:
            pkg, addr = reader.read_packet()
        except socket.timeout:
            continue
        
        if pkg == END.encode():
            print(">>> Transferencia finalizada.")
            work_done = True
            reader.send_packet(expected_seq.to_bytes(4, "big"), sender_addr)
            arch.archivo.close()
            break
        
        # Parsear paquete Go Back N
        seq_num, data_len, pkg_id, data = arch.recv_pckg_go_back_n(pkg)
        print(f">>> Recibí seq={seq_num}, esperado={expected_seq}, pkg_id={pkg_id}, len={data_len}")
        
        if pkg_id == expected_seq:
            # Paquete correcto: escribir datos y enviar ACK
            arch.archivo.write(data)
            arch.archivo.flush()
            reader.send_packet(expected_seq.to_bytes(4, "big"), sender_addr)
            print(f">>> Enviando ACK{expected_seq}")
            expected_seq += 1
        else:
            # Paquete fuera de orden: reenviar ACK del último válido
            # Si expected_seq es 0, enviar ACK 0 (no -1)
            ack_to_send = max(0, expected_seq - 1)
            reader.send_packet(ack_to_send.to_bytes(4, "big"), sender_addr)
            print(f">>> Paquete fuera de orden, reenviando ACK{ack_to_send}")
        