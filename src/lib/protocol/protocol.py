import socket
from lib.protocol.archive import ArchiveSender, ArchiveRecv

def handshake(sock: socket, name: str, type: str, protocol: str, server_addr):
    """
    Realiza el handshake inicial con el servidor.
    Envía el tipo de conexión (UPLOAD o DOWNLOAD), el protocolo (SW o GBN) y el nombre del archivo.
    """
    stop_and_wait(sock, type.encode(), 0, server_addr)
    stop_and_wait(sock, protocol.encode(), 1, server_addr)
    stop_and_wait(sock, name.encode(), 2, server_addr)
    
    # Delay para evitar que se mezclen paquetes del handshake con los de datos
    import time
    time.sleep(1.0)
  
def stop_and_wait(sock: socket, msg, ack_number, addr):
    """
    Envía un mensaje usando el protocolo Stop and Wait.
    Reenvía el mensaje hasta recibir confirmación ACK.
    """
    sock.sendto(msg, addr)
    ack_recv = False
    retry_count = 0
    max_retries = 70
    
    while not ack_recv and retry_count < max_retries:
        sock.settimeout(0.1)  # Timeout intermedio
        try:
            pkg, recv_addr = sock.recvfrom(1024)
            # Verificar que el paquete viene de la dirección correcta
            print(pkg)
            value = int.from_bytes(pkg, "big")
            if recv_addr == addr and len(pkg) == 4 and (value == ack_number) :  # ACK de 4 bytes
                ack_recv = True
                ack_value = int.from_bytes(pkg, "big")
                print(f"ACK recibido: {ack_value}")
            elif recv_addr != addr:
                print(f"Paquete de dirección incorrecta: {recv_addr} (esperaba {addr})")
            elif len(pkg) != 4:
                print(f"Paquete no es ACK válido (len={len(pkg)}), ignorando...")
        except socket.timeout:
            retry_count += 1
            print(f"timeout, no recibi ACK (intento {retry_count}/{max_retries})")
            sock.sendto(msg, addr)
    
    if not ack_recv:
        print(f"Error: No se pudo completar el handshake después de {max_retries} intentos")
        raise Exception("Handshake failed")

def upload_go_back_n(sock: socket, arch: ArchiveSender, end, window_sz, server_addr, timeout):
    """
    Sube un archivo usando el protocolo Go Back N.
    Utiliza una ventana deslizante para enviar múltiples paquetes sin esperar confirmación.
    """
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

    print(f">>> Cliente: Iniciando upload GBN con ventana={window_sz}")
    while not end:
        print(f">>> Cliente: Ciclo principal - end={end}, file_finished={file_finished}, pkgs_not_ack={len(pkgs_not_ack)}")
        # Fase 1: Enviar paquetes hasta llenar la ventana o terminar el archivo
        while(len(pkgs_not_ack) < window_sz and not file_finished):
            print(f">>> Cliente: Enviando paquete pkg_id={pkg_id}")
            pkg, pkg_id_bytes = arch.next_pkg_go_back_n(pkg_id)  # Usar pkg_id completo
            if pkg is None:
                # Crear paquete END con flag_end = 1
                first_byte = 1  # flag_end = 1 para END
                pkg = first_byte.to_bytes(1, "big") + (0).to_bytes(2, "big") + (pkg_id).to_bytes(4, "big")  # data_len = 0, pkg_id = pkg_id
                pkg_id_bytes = (pkg_id).to_bytes(4, "big")  # pkg_id = pkg_id para END
                file_finished = True
                print(f">>> Cliente: Creando paquete END con pkg_id={pkg_id}")
            
            sock.sendto(pkg, server_addr)
            print(f">>> Cliente: Envié paquete pkg_id={pkg_id} (len={len(pkg)})")
            
            # Agregar a pkgs_not_ack, incluyendo el paquete END
            pkgs_not_ack[pkg_id_bytes] = pkg
            pkg_id += 1
        

        # Fase 2: Esperar ACKs
        print(f">>> Cliente: Terminé de enviar paquetes, esperando ACKs. Paquetes sin ACK: {len(pkgs_not_ack)}")

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
            
            print(f">>> Cliente: Recibí ACK: {pkg} de {recv_addr}")
            value = int.from_bytes(pkg, "big")
            if len(pkg) == 4 and value != -1:
                ack_num = int.from_bytes(pkg, "big")
                print(f">>> Cliente: Procesando ACK {ack_num} (bytes: {pkg})")
                if ack_num > last_ack:
                    to_remove = []
                    for pkg_id_bytes_key in pkgs_not_ack:
                        pkg_id_num = int.from_bytes(pkg_id_bytes_key, 'big')
                        if pkg_id_num < ack_num:
                            to_remove.append(pkg_id_bytes_key)
                            print(f">>> Cliente: Removiendo paquete {pkg_id_num} de la ventana")
                    for pkg_id_bytes_key in to_remove:
                        del pkgs_not_ack[pkg_id_bytes_key]
                    
                    # Actualizar last_ack al ACK recibido
                    last_ack = ack_num
                    
                    print(f">>> Cliente: Después del ACK - file_finished={file_finished}, pkgs_not_ack={len(pkgs_not_ack)}")
                    if file_finished and not pkgs_not_ack:
                        print(">>> Cliente: Archivo terminado y todos los paquetes confirmados, saliendo...")
                        end = True
                    break
                else:
                    print(f">>> Cliente: ACK {ack_num} es menor que el último ACK {last_ack}, ignorando...")
                    continue

        # Restaurar timeout del socket
        sock.settimeout(None)
        
        if time.time() - start_time >= timeout:
            print(f">>> Cliente: Timeout esperando ACKs - file_finished={file_finished}, pkgs_not_ack={len(pkgs_not_ack)}")
            
            # Verificar timeout global
            if time.time() - transfer_start_time >= max_transfer_time:
                print(f">>> Cliente: TIMEOUT GLOBAL - Transfer excedió {max_transfer_time} segundos, abortando...")
                return
            
            if file_finished and not pkgs_not_ack:
                # Si terminamos el archivo y no hay paquetes sin confirmar, salir
                print(">>> Cliente: Archivo terminado y no hay paquetes sin confirmar, saliendo...")
                end = True
            else:
                # Verificar reintentos por paquete antes de reenviar
                packets_to_remove = []
                packets_to_retry = []
                
                for pkg_id_bytes_key, value in pkgs_not_ack.items():
                    pkg_num = int.from_bytes(pkg_id_bytes_key, 'big')
                    retry_count = pkg_retry_count.get(pkg_num, 0)
                    
                    if retry_count >= max_retries_per_packet:
                        print(f">>> Cliente: Paquete {pkg_num} alcanzó máximo de reintentos ({max_retries_per_packet}), asumirndo entregado")
                        packets_to_remove.append(pkg_id_bytes_key)
                    else:
                        packets_to_retry.append((pkg_id_bytes_key, value, pkg_num))
                        pkg_retry_count[pkg_num] = retry_count + 1
                
                # Remover paquetes que alcanzaron el límite
                for pkg_key in packets_to_remove:
                    del pkgs_not_ack[pkg_key]
                
                # Reenviar paquetes que no alcanzaron el límite
                if packets_to_retry:
                    print(f">>> Cliente: Reenviando {len(packets_to_retry)} paquetes sin ACK")
                    for pkg_id_bytes_key, value, pkg_num in packets_to_retry:
                        sock.sendto(value, server_addr)
                        print(f">>> Cliente: Reenvié paquete {pkg_num} (intento {pkg_retry_count[pkg_num]})")
                else:
                    print(">>> Cliente: Todos los paquetes alcanzaron el límite de reintentos, asumiendo transferencia completa")
                    end = True

def download_go_back_n(sock: socket, arch: ArchiveRecv, server_addr, timeout):
    """
    Descarga un archivo usando el protocolo Go Back N.
    Funciona como stop and wait desde el lado del receptor.
    """
    expected_pkg_id = 3
    work_done = False
    print(">>> Cliente: empezando a recibir archivo con Go Back N...")

    while not work_done:
        try:
            print(f">>> Cliente: Esperando paquete del servidor (expected_pkg_id={expected_pkg_id})...")
            sock.settimeout(timeout)
            pkg, recv_addr = sock.recvfrom(1024)
            print(f">>> Cliente: Recibí paquete de {len(pkg)} bytes de {recv_addr}")
            
            # Verificar que el paquete viene del servidor correcto
            if recv_addr != server_addr:
                print(f">>> Cliente: Paquete de dirección incorrecta {recv_addr} (esperaba {server_addr}), ignorando...")
                continue
                
            # Filtrar paquetes que no son del protocolo de datos (menos de 7 bytes)
            if len(pkg) < 7:
                print(f">>> Cliente: Recibí paquete no válido del protocolo (len={len(pkg)}), ignorando...")
                continue
                
        except socket.timeout:
            print(f">>> Cliente: Timeout esperando paquetes del servidor (expected_pkg_id={expected_pkg_id})")
            continue

        flag_end, data_len, pkg_id, data = arch.recv_pckg_go_back_n(pkg)
        print(f">>> Cliente: Procesando paquete - flag_end={flag_end}, pkg_id={pkg_id}, expected_pkg_id={expected_pkg_id}, data_len={data_len}")

        if flag_end == 1:
            print(">>> Cliente: Transferencia finalizada (paquete END recibido)")
            work_done = True
            # Enviar ACK para el paquete END
            sock.sendto(pkg_id.to_bytes(4, "big"), server_addr)  # ACK de 4 bytes
            print(f">>> Cliente: Envié ACK final para paquete END {pkg_id}")
            break

        if pkg_id == expected_pkg_id:
            # Paquete en orden, procesar y enviar ACK
            print(f">>> Cliente: Paquete en orden, escribiendo {data_len} bytes")
            arch.write_data(data)
            sock.sendto(pkg_id.to_bytes(4, "big"), server_addr)
            print(f">>> Cliente: Envié ACK{pkg_id} para paquete en orden")
            expected_pkg_id += 1
        else:
            # Paquete fuera de orden, enviar ACK del último paquete correcto
            if expected_pkg_id > 0:
                last_ack = expected_pkg_id - 1
            else:
                last_ack = 0  # Si es el primer paquete y está fuera de orden
            sock.sendto(last_ack.to_bytes(4, "big"), server_addr)
            print(f">>> Cliente: Paquete fuera de orden (recibí {pkg_id}, esperaba {expected_pkg_id}), reenvío ACK{last_ack}")
    
    print(">>> Cliente: cerrando archivo...")
    arch.archivo.close()