import socket
import queue
from lib.protocol.archive import ArchiveSender, ArchiveRecv
import os
import time
from lib.protocol.utils import setup_logging
from lib.constants import STOP_AND_WAIT

################################### PROTOCOLO DEL SERVIDOR ################################################################
def handshake_server(channel: queue.Queue, addr, writing_queue, verbose=False, quiet=False):
    logger = setup_logging('protocol.server.handshake', verbose, quiet)
    try:
        logger.debug(f">>> Server: Iniciando manejo de cliente {addr}")
        conexion_type = channel.get(block=True)
        logger.debug(f">>> Server: Recibí conexion_type de {addr}")

        writing_queue.put(((0).to_bytes(4, "big"), addr))
        logger.debug(f">>> Server: Envié ACK de conexion_type a {addr}")
        
        # Esperar protocol con timeout
        try:
            queue_size = channel.qsize()
            #print(f">>> Server: Cola de {addr} tiene {queue_size} paquetes antes de esperar protocol")
            protocol = channel.get(block=True, timeout=2.0)  # Timeout aumentado
            logger.debug(f">>> Server: recibí protocol={protocol} de {addr}")
        except queue.Empty:
            queue_size = channel.qsize()
            #print(f">>> Server: timeout esperando protocol de {addr}, cola tiene {queue_size} paquetes")
            return

        # Reenviar ACK si el cliente reenvía el mismo paquete
        while protocol == conexion_type:  # entonces el ACK se perdio, reenviamos
            logger.debug(f">>> Server: Cliente reenvió conexion_type, reenviando ACK a {addr}")
            writing_queue.put(((0).to_bytes(4, "big"), addr))
            try:
                protocol = channel.get(block=True, timeout=2.0)  # Timeout aumentado
            except queue.Empty:
                logger.warning(f"Timeout esperando protocol de {addr}")
                return

        writing_queue.put(((1).to_bytes(4, "big"), addr))
        logger.debug(f">>> Server: envié ACK de protocol a {addr}")
        
        # Esperar name con timeout
        try:
            queue_size = channel.qsize()
            #print(f">>> Server: Cola de {addr} tiene {queue_size} paquetes antes de esperar name")
            name = channel.get(block=True, timeout=2.0)  # Timeout aumentado
            logger.debug(f">>> Server: recibí name={name} de {addr}")
        except queue.Empty:
            queue_size = channel.qsize()
            #print(f">>> Server: timeout esperando name de {addr}, cola tiene {queue_size} paquetes")
            return

        # Reenviar ACK si el cliente reenvía el mismo paquete
        while name == protocol:  # entonces el ACK se perdio, reenviamos
            logger.debug(f">>> Server: cliente reenvió protocol, reenviando ACK a {addr}")
            writing_queue.put(((1).to_bytes(4, "big"), addr))
            try:
                name = channel.get(block=True, timeout=2.0)  # Timeout aumentado
            except queue.Empty:
                logger.warning(f">>> Server: timeout esperando name de {addr}")
                return

        name = name.decode()
        protocol = protocol.decode()
        conexion_type = conexion_type.decode()
        #logger.debug(f">>> Server: conexion_type={conexion_type}, protocol={protocol}, name={name}, addr={addr}")
    except Exception as e:
        logger.warning(f">>> Server: Error en manage_client: {e}")
        return
    
    return conexion_type, protocol, name

def download_from_client(name, writing_queue: queue.Queue, addr, window_sz, channel, timeout, verbose=False, quiet=False):
    """
    Envía archivo al cliente usando Go Back N.
    Utiliza una ventana deslizante para enviar n paquetes y luego esperar ACKs.
    """
    logger = setup_logging('protocol.server.download', verbose, quiet)
    # Usar path absoluto
    current_dir = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.join(current_dir, "..", "server")
    target_dir = os.path.abspath(target_dir) 

    path = os.path.join(target_dir, "storage", name)

    if not os.path.exists(path):
        logger.error(f">>> Server: archivo no encontrado: {path}")
        return
    logger.info(f">>> Server: archivo encontrado, empezando envío con Go Back N...")
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
                logger.debug(f">>> Server: creando paquete END con pkg_id={pkg_id}")
            writing_queue.put((pkg, addr))
            logger.info(f">>> Server: envió paquete con flag_end={pkg[0] & 1}, pkg_id={pkg_id} (len={len(pkg)})")
            
            # Siempre agregar a pkgs_not_ack, incluyendo el paquete END
            pkgs_not_ack[pkg_id_bytes] = pkg
            pkg_id += 1
        
        # Fase 2: Esperar ACKs
        print(f">>> Server: termine de enviar los paquetes, tengo que esperar ACK. Paquetes sin ACK: {len(pkgs_not_ack)}")
        
        try:
            queue_size_before = channel.qsize()
            #print(f">>> Server: Cola de {addr} tiene {queue_size_before} paquetes antes de get() en download")
            pkg = channel.get(block=True, timeout=timeout)
            queue_size_after = channel.qsize()
            #print(f">>> Server: Cola de {addr} tiene {queue_size_after} paquetes después de get() en download, ACK recibido: {pkg}")
            if len(pkg) == 4:
                ack_num = int.from_bytes(pkg, "big")
                logger.debug(f">>> Server: ACK recibido para paquete {ack_num}")
                
                # Remover todos los paquetes con pkg_id <= ack_num
                to_remove = []
                for pkg_id_bytes_key in pkgs_not_ack:
                    pkg_id_num = int.from_bytes(pkg_id_bytes_key, 'big')
                    if pkg_id_num <= ack_num:
                        to_remove.append(pkg_id_bytes_key)
                        logger.debug(f">>> Server: removiendo paquete {pkg_id_num} de la ventana")
                
                for pkg_id_bytes_key in to_remove:
                    del pkgs_not_ack[pkg_id_bytes_key]
                
                # Si terminamos el archivo y no hay paquetes sin confirmar, salir
                if file_finished and not pkgs_not_ack:
                    logger.debug(">>> Server: todos los paquetes confirmados, finalizando transferencia")
                    end = True

        except queue.Empty:
            if file_finished and not pkgs_not_ack:
                # Si terminamos el archivo y no hay paquetes sin confirmar, salir
                logger.info(">>> Server: timeout pero no hay paquetes pendientes, finalizando")
                end = True
            else:
                logger.warning(">>> Server: timeout, no recibi ACKs, reenvio los n paquetes")
                for value in pkgs_not_ack.values():
                    writing_queue.put((value, addr))
        except ConnectionResetError:
                logger.error(">>> Server: Conexión reseteada durante download")
                return
        except Exception as e:
                logger.error(f">>> Server: Error durante download: {e}")
                return

def upload_from_client(name, channel, writing_queue: queue.Queue, addr, protocol=None, sock=None, verbose=False, quiet=False):
    """
    Recibe archivo del cliente usando Go Back N o Stop and Wait.
    Protocol determina la lógica de ACK:
    - STOP_AND_WAIT: ACK del siguiente paquete esperado (pkg_id+1)
    - GO_BACK_N: ACK del último paquete recibido en orden (expected_pkg_id-1) para fuera de orden
    """
    logger = setup_logging('protocol.server.upload', verbose, quiet)
    logger.debug(f">>> Server: upload_from_client_go_back_n iniciado para {name} desde {addr}")
    # Usar path absoluto
    current_dir = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.join(current_dir, "..", "server")
    target_dir = os.path.abspath(target_dir)
    path = os.path.join(target_dir, "storage", name)
    arch = ArchiveRecv(path)
    expected_pkg_id = 3
    work_done = False
    
    logger.debug(f">>> Server: upload_from_client_go_back_n esperando paquetes de {addr}")
    
    while not work_done:
        try:
            pkg = channel.get(block=True, timeout=30.0)  # Timeout de 30 segundos
        except queue.Empty:
            logger.warning(f">>> Server: Timeout esperando paquetes de {addr}")
            break
        
        flag_end, _, pkg_id, data = arch.recv_pckg_go_back_n(pkg)
        
        logger.debug(f">>> Server: recibí paquete flag_end={flag_end}, pkg_id={pkg_id}, esperado={expected_pkg_id}")
        
        
        if pkg_id == expected_pkg_id:
            if flag_end == 1:
                logger.debug(f">>> Server: paquete final recibido (flag_end=1), pkg_id={pkg_id}")
                ack_data = (pkg_id+1).to_bytes(4, "big")
                for i in range(1, 11):
                    writing_queue.put((ack_data, addr))
                
                logger.debug(f">>> Server: finalizando transfer para {addr}")
                work_done = True
            else:
                arch.write_data(data)
                ack_data = (pkg_id+1).to_bytes(4, "big")
                writing_queue.put((ack_data, addr))
                expected_pkg_id += 1
        else:
            writing_queue.put((expected_pkg_id.to_bytes(4, "big"), addr))
          

        
    
    # Cerrar archivo al terminar
    arch.archivo.close()
    logger.info(f">>> Server: upload completado para {name} desde {addr}, archivo cerrado")

################################### FINAL PROTOCOLO SERVER ################################################################








################################### PROTOCOLO DEL CLIENTE #################################################################
def handshake(sock: socket, name: str, type: str, protocol: str, server_addr, verbose=False, quiet=False):
    """
    Realiza el handshake inicial con el servidor.
    Envía el tipo de conexión (UPLOAD o DOWNLOAD), el protocolo (SW o GBN) y el nombre del archivo.
    """
    logger = setup_logging('protocol.client.handshake', verbose, quiet)
    logger.info(f"Iniciando handshake: type={type}, protocol={protocol}, name={name}")
    stop_and_wait(sock, type.encode(), 0, server_addr)
    stop_and_wait(sock, protocol.encode(), 1, server_addr)
    stop_and_wait(sock, name.encode(), 2, server_addr)
    
    logger.info("Handshake completado")

    # Delay para evitar que se mezclen paquetes del handshake con los de datos
    import time
    time.sleep(1.0)
  
def stop_and_wait(sock: socket, msg, ack_number, addr, verbose=False, quiet=False):
    """
    Envía un mensaje usando el protocolo Stop and Wait.
    Reenvía el mensaje hasta recibir confirmación ACK.
    """
    logger = setup_logging('protocol.client.saw', verbose, quiet)
    sock.sendto(msg, addr)
    ack_recv = False
    retry_count = 0
    max_retries = 70
    
    while not ack_recv and retry_count < max_retries:
        sock.settimeout(0.1)  # Timeout intermedio
        try:
            pkg, recv_addr = sock.recvfrom(1024)
            # Verificar que el paquete viene de la dirección correcta
            value = int.from_bytes(pkg, "big")
            if recv_addr == addr and len(pkg) == 4 and (value == ack_number) :  # ACK de 4 bytes
                ack_recv = True
                ack_value = int.from_bytes(pkg, "big")
                logger.debug(f"ACK recibido: {ack_value}")
            elif recv_addr != addr:
                logger.debug(f"Paquete de dirección incorrecta: {recv_addr} (esperaba {addr})")
            elif len(pkg) != 4:
                logger.debug(f"Paquete no es ACK válido (len={len(pkg)}), ignorando...")
        except socket.timeout:
            retry_count += 1
            logger.warning(f"timeout, no recibi ACK (intento {retry_count}/{max_retries})")
            sock.sendto(msg, addr)
    
    if not ack_recv:
        logger.error(f"Error: No se pudo completar el handshake después de {max_retries} intentos")
        raise Exception("Handshake failed")

def upload(sock: socket, arch: ArchiveSender, end, window_sz, server_addr, timeout, verbose=False, quiet=False):
    """
    Sube un archivo usando el protocolo Go Back N.
    Utiliza una ventana deslizante para enviar múltiples paquetes sin esperar confirmación.
    """

    logger = setup_logging('protocol.client.upload', verbose, quiet)

    pkg_id = 3
    pkgs_not_ack = {}
    file_finished = False
    last_ack = 0
    
    # Control de reintentos y timeout global
    pkg_retry_count = {}  # Contador de reintentos por paquete
    max_retries_per_packet = 70  # Máximo 10 reintentos por paquete
    import time
    transfer_start_time = time.time()
    max_transfer_time = 300  # 5 minutos máximo para transferencia completa

    logger.info(f">>> Cliente: Iniciando upload GBN con ventana={window_sz}")
    while not end:
        logger.debug(f">>> Cliente: Ciclo principal - end={end}, file_finished={file_finished}, pkgs_not_ack={len(pkgs_not_ack)}")
        # Fase 1: Enviar paquetes hasta llenar la ventana o terminar el archivo
        while(len(pkgs_not_ack) < window_sz and not file_finished):
            logger.debug(f">>> Cliente: Enviando paquete pkg_id={pkg_id}")
            pkg, pkg_id_bytes = arch.next_pkg_go_back_n(pkg_id)  # Usar pkg_id completo
            if pkg is None:
                # Crear paquete END con flag_end = 1
                first_byte = 1  # flag_end = 1 para END
                pkg = first_byte.to_bytes(1, "big") + (0).to_bytes(2, "big") + (pkg_id).to_bytes(4, "big")  # data_len = 0, pkg_id = pkg_id
                pkg_id_bytes = (pkg_id).to_bytes(4, "big")  # pkg_id = pkg_id para END
                file_finished = True
                logger.debug(f">>> Cliente: Creando paquete END con pkg_id={pkg_id}")
            
            sock.sendto(pkg, server_addr)
            logger.debug(f">>> Cliente: Envié paquete pkg_id={pkg_id} (len={len(pkg)})")
            
            # Agregar a pkgs_not_ack, incluyendo el paquete END
            pkgs_not_ack[pkg_id_bytes] = pkg
            pkg_id += 1
        

        # Fase 2: Esperar ACKs
        logger.debug(f">>> Cliente: Terminé de enviar paquetes, esperando ACKs. Paquetes sin ACK: {len(pkgs_not_ack)}")

        import time
        start_time = time.time()
        sock.settimeout(timeout)  # Timeout pequeño para no bloquearse indefinidamente
        while time.time() - start_time < timeout:
            try:
                pkg, recv_addr = sock.recvfrom(1024)
                if pkg is None:
                    continue
            except socket.timeout:
                # Timeout del socket, continuar para verificar si se agotó el timeout principal
                continue
            
            logger.debug(f">>> Cliente: Recibí ACK: {pkg} de {recv_addr}")
            value = int.from_bytes(pkg, "big")
            if len(pkg) == 4:
                ack_num = int.from_bytes(pkg, "big")
                logger.debug(f">>> Cliente: Procesando ACK {ack_num} (bytes: {pkg})")
                if ack_num > last_ack:
                    to_remove = []
                    for pkg_id_bytes_key in pkgs_not_ack:
                        pkg_id_num = int.from_bytes(pkg_id_bytes_key, 'big')
                        if pkg_id_num < ack_num:
                            to_remove.append(pkg_id_bytes_key)
                            logger.debug(f">>> Cliente: Removiendo paquete {pkg_id_num} de la ventana")
                    for pkg_id_bytes_key in to_remove:
                        del pkgs_not_ack[pkg_id_bytes_key]
                    
                    # Actualizar last_ack al ACK recibido
                    last_ack = ack_num
                    
                    logger.debug(f">>> Cliente: Después del ACK - file_finished={file_finished}, pkgs_not_ack={len(pkgs_not_ack)}")
                    if file_finished and not pkgs_not_ack:
                        logger.info(">>> Cliente: Archivo terminado y todos los paquetes confirmados, saliendo...")
                        end = True
                    break
                else:
                    logger.debug(f">>> Cliente: ACK {ack_num} es menor que el último ACK {last_ack}, ignorando...")
                    continue

        # Restaurar timeout del socket
        sock.settimeout(None)
        
        if time.time() - start_time >= timeout:
            logger.warning(f">>> Cliente: Timeout esperando ACKs - file_finished={file_finished}, pkgs_not_ack={len(pkgs_not_ack)}")
            
            # Verificar timeout global
            if time.time() - transfer_start_time >= max_transfer_time:
                logger.error(f">>> Cliente: TIMEOUT GLOBAL - Transfer excedió {max_transfer_time} segundos, abortando...")
                return
            
            if file_finished and not pkgs_not_ack:
                # Si terminamos el archivo y no hay paquetes sin confirmar, salir
                logger.info(">>> Cliente: Archivo terminado y no hay paquetes sin confirmar, saliendo...")
                end = True
            else:
                # Verificar reintentos por paquete antes de reenviar
                packets_to_remove = []
                packets_to_retry = []
                
                for pkg_id_bytes_key, value in pkgs_not_ack.items():
                    pkg_num = int.from_bytes(pkg_id_bytes_key, 'big')
                    retry_count = pkg_retry_count.get(pkg_num, 0)
                    
                    if retry_count >= max_retries_per_packet:
                        logger.warning(f">>> Cliente: Paquete {pkg_num} alcanzó máximo de reintentos ({max_retries_per_packet}), asumirndo entregado")
                        packets_to_remove.append(pkg_id_bytes_key)
                    else:
                        packets_to_retry.append((pkg_id_bytes_key, value, pkg_num))
                        pkg_retry_count[pkg_num] = retry_count + 1
                
                # Remover paquetes que alcanzaron el límite
                for pkg_key in packets_to_remove:
                    del pkgs_not_ack[pkg_key]
                
                # Reenviar paquetes que no alcanzaron el límite
                if packets_to_retry:
                    logger.warning(f">>> Cliente: Reenviando {len(packets_to_retry)} paquetes sin ACK")
                    for pkg_id_bytes_key, value, pkg_num in packets_to_retry:
                        sock.sendto(value, server_addr)
                        logger.debug(f">>> Cliente: Reenvié paquete {pkg_num} (intento {pkg_retry_count[pkg_num]})")
                else:
                    logger.warning(">>> Cliente: Todos los paquetes alcanzaron el límite de reintentos, asumiendo transferencia completa")
                    end = True

def download(sock: socket, arch: ArchiveRecv, server_addr, timeout, verbose=False, quiet=False):
    """
    Descarga un archivo usando el protocolo Go Back N.
    Funciona como stop and wait desde el lado del receptor.
    """
    logger = setup_logging('client.download', verbose, quiet)

    logger.info(">>> Cliente: empezando a recibir archivo con Go Back N...")
    expected_pkg_id = 3
    work_done = False

    while not work_done:
        try:
            logger.debug(f">>> Cliente: Esperando paquete del servidor (expected_pkg_id={expected_pkg_id})...")
            sock.settimeout(timeout)
            pkg, recv_addr = sock.recvfrom(1024)
            logger.debug(f">>> Cliente: Recibí paquete de {len(pkg)} bytes de {recv_addr}")
            
            # Verificar que el paquete viene del servidor correcto
            if recv_addr != server_addr:
                logger.warning(f">>> Cliente: Paquete de dirección incorrecta {recv_addr} (esperaba {server_addr}), ignorando...")
                continue
                
            # Filtrar paquetes que no son del protocolo de datos (menos de 7 bytes)
            if len(pkg) < 7:
                logger.warning(f">>> Cliente: Recibí paquete no válido del protocolo (len={len(pkg)}), ignorando...")
                continue
                
        except socket.timeout:
            logger.debug(f">>> Cliente: Timeout esperando paquetes del servidor (expected_pkg_id={expected_pkg_id})")
            continue

        flag_end, data_len, pkg_id, data = arch.recv_pckg_go_back_n(pkg)
        logger.debug(f">>> Cliente: Procesando paquete - flag_end={flag_end}, pkg_id={pkg_id}, expected_pkg_id={expected_pkg_id}, data_len={data_len}")

        if pkg_id == expected_pkg_id:
            if flag_end == 1:
                logger.info(">>> Cliente: Transferencia finalizada (paquete END recibido)")
                work_done = True
                # Enviar ACK para el paquete END
                for i in range(1,11):
                    sock.sendto(pkg_id.to_bytes(4, "big"), server_addr)  # ACK de 4 bytes
                logger.debug(f">>> Cliente: Envié ACK final para paquete END {pkg_id}")
            
            else:
                # Paquete en orden, procesar y enviar ACK
                logger.debug(f">>> Cliente: Paquete en orden, escribiendo {data_len} bytes")
                arch.write_data(data)
                sock.sendto(pkg_id.to_bytes(4, "big"), server_addr)
                logger.debug(f">>> Cliente: Envié ACK{pkg_id} para paquete en orden")
                expected_pkg_id += 1
        else:
            # Paquete fuera de orden, enviar ACK del último paquete correcto
            if expected_pkg_id > 0:
                last_ack = expected_pkg_id - 1
            else:
                last_ack = 0  # Si es el primer paquete y está fuera de orden
            sock.sendto(last_ack.to_bytes(4, "big"), server_addr)
            logger.debug(f">>> Cliente: Paquete fuera de orden (recibí {pkg_id}, esperaba {expected_pkg_id}), reenvío ACK{last_ack}")
        
        

       
    
    logger.warning(">>> Cliente: cerrando archivo...")
    arch.archivo.close()

################################### FIN PROTOCOLO DE CLIENTE #################################################################