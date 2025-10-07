from mininet.net import Mininet
from mininet.cli import CLI
from mininet.node import Controller, OVSKernelSwitch
from mininet.link import TCLink

def start_network():
    net = Mininet(controller=Controller, switch=OVSKernelSwitch, link=TCLink)

    # Add controller with explicit executable
    net.addController("c0", controller=Controller, command="ovs-testcontroller")

    # Add hosts and switch (usar rutas absolutas)
    import os
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    h1 = net.addHost("h1", ip="10.0.0.1")
    h2 = net.addHost("h2", ip="10.0.0.2")
    h3 = net.addHost("h3", ip="10.0.0.3")
    h4 = net.addHost("h4", ip="10.0.0.4")
    h5 = net.addHost("h5", ip="10.0.0.5")
    s1 = net.addSwitch("s1")

    net.addLink(h1, s1, loss=10)
    net.addLink(h2, s1)
    net.addLink(h3, s1)
    net.addLink(h4, s1)
    net.addLink(h5, s1)
    net.start()

    # Crear directorio para archivos de wireshark si no existe
    wireshark_dir = os.path.join(base_path, "wireshark_files")
    if not os.path.exists(wireshark_dir):
        os.makedirs(wireshark_dir)
    
    # Crear directorio para logs si no existe
    logs_dir = os.path.join(base_path, "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # Start tcpdump on server (h1)
    tcpdump_h1 = h1.popen(f"tcpdump -i h1-eth0 udp -w {wireshark_dir}/h1_capture.pcap")

    # Start tcpdump on client (h2)
    tcpdump_h2 = h2.popen(f"tcpdump -i h2-eth0 udp -w {wireshark_dir}/h2_capture.pcap")

    # Start tcpdump on client (h3)
    tcpdump_h3 = h3.popen(f"tcpdump -i h3-eth0 udp -w {wireshark_dir}/h3_capture.pcap")
    # Start tcpdump on client (h4)
    tcpdump_h4 = h4.popen(f"tcpdump -i h4-eth0 udp -w {wireshark_dir}/h4_capture.pcap")
    # Start tcpdump on client (h5)
    tcpdump_h5 = h5.popen(f"tcpdump -i h5-eth0 udp -w {wireshark_dir}/h5_capture.pcap")

    # Usar ruta src para todos los comandos
    src_path = os.path.join(base_path, "src")
    storage_path = os.path.join(base_path, "src/lib/server/storage")

    # Copiar archivo de prueba al servidor
    test_file_path = os.path.join(base_path, "test.png")
    h1.cmd(f'cp {test_file_path} {storage_path}/test.png')
    
    # Copiar archivo de prueba a los hosts de upload
    h2.cmd(f'cp {test_file_path} /tmp/test.png')
    h3.cmd(f'cp {test_file_path} /tmp/test.png')
    
    # Abrir terminales SIN ejecutar comandos automáticamente
    # El usuario deberá copiar y pegar los comandos manualmente
    
    # Terminal para servidor (h1)
    h1.cmd(f'xterm -hold -e "cd {src_path}; echo \'=== SERVIDOR (h1) ===\'; echo \'Copiar y ejecutar:\'; echo \'python3 start-server.py -H 10.0.0.1 -p 5005 -v 2>&1 | tee {logs_dir}/server.log\'; echo \'\'; bash" &')
    
    # Terminal para cliente upload SW (h2)
    h2.cmd(f'xterm -hold -e "cd {src_path}; echo \'=== CLIENTE UPLOAD SW (h2) ===\'; echo \'Copiar y ejecutar:\'; echo \'python3 upload.py -s /tmp/test.png -n uploadsw.png -r SW -H 10.0.0.1 -p 5005 -v 2>&1 | tee {logs_dir}/client_upload_sw.log\'; echo \'\'; bash" &')
    
    # Terminal para cliente upload GBN (h3)
    h3.cmd(f'xterm -hold -e "cd {src_path}; echo \'=== CLIENTE UPLOAD GBN (h3) ===\'; echo \'Copiar y ejecutar:\'; echo \'python3 upload.py -s /tmp/test.png -n uploadgbn.png -r GBN -H 10.0.0.1 -p 5005 -v 2>&1 | tee {logs_dir}/client_upload_gbn.log\'; echo \'\'; bash" &')
    
    # Terminal para cliente download SW (h4)
    h4.cmd(f'xterm -hold -e "cd {src_path}; echo \'=== CLIENTE DOWNLOAD SW (h4) ===\'; echo \'Copiar y ejecutar:\'; echo \'python3 download.py -d ./downloadsw.png -n test.png -r SW -H 10.0.0.1 -p 5005 -v 2>&1 | tee {logs_dir}/client_download_sw.log\'; echo \'\'; bash" &')
    
    # Terminal para cliente download GBN (h5)
    h5.cmd(f'xterm -hold -e "cd {src_path}; echo \'=== CLIENTE DOWNLOAD GBN (h5) ===\'; echo \'Copiar y ejecutar:\'; echo \'python3 download.py -d ./downloadgbn.png -n test.png -r GBN -H 10.0.0.1 -p 5005 -v 2>&1 | tee {logs_dir}/client_download_gbn.log\'; echo \'\'; bash" &')

    print(f"\n=== Red iniciada ===")
    print(f"Se abrieron 5 terminales xterm:")
    print(f"  - h1: SERVIDOR")
    print(f"  - h2: Cliente Upload Stop & Wait")
    print(f"  - h3: Cliente Upload Go Back N")
    print(f"  - h4: Cliente Download Stop & Wait")
    print(f"  - h5: Cliente Download Go Back N")
    print(f"\nEn cada terminal verás el comando a ejecutar.")
    print(f"Copia y pega el comando en la terminal correspondiente.")
    print(f"\nCapturas de red: {wireshark_dir}/")
    print(f"Logs de aplicación: {logs_dir}/")
    print(f"\nPrimero ejecuta el servidor (h1), luego los clientes.")
    print(f"Presiona 'exit' en la CLI de Mininet para terminar\n")
    
    CLI(net)
    
    print("\n=== Terminando red ===")
    h1.cmd("killall xterm")
    h2.cmd("killall xterm")
    h3.cmd("killall xterm")
    h4.cmd("killall xterm")
    h5.cmd("killall xterm")
    tcpdump_h1.terminate()
    tcpdump_h2.terminate()
    tcpdump_h3.terminate()
    tcpdump_h4.terminate()
    tcpdump_h5.terminate()
    
    print(f"Logs guardados en: {logs_dir}/")
    print(f"Capturas guardadas en: {wireshark_dir}/")
    net.stop()


if __name__ == "__main__":
    start_network()