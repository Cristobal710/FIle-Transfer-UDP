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

    # Usar rutas absolutas para los comandos
    server_path = os.path.join(base_path, "src/lib", "server")
    client_path = os.path.join(base_path, "src/lib", "client")


    # Copiar archivo de prueba al servidor
    test_file_path = os.path.join(base_path, "test.png")
    h1.cmd(f'cp {test_file_path} {server_path}/storage/test.png')
    
    # Levantar servidor primero
    h1.cmd(f'xterm -hold -e "cd {server_path}; python3 server.py start-server -H 10.0.0.1 -p 5005 2>&1 | tee {logs_dir}/server.log; bash" &')
    
    # Esperar un poco para que el servidor se inicie
    import time
    time.sleep(2)
    
    # Copiar archivo de prueba a los hosts de upload
    h2.cmd(f'cp {test_file_path} /tmp/test.png')
    h3.cmd(f'cp {test_file_path} /tmp/test.png')
    
    # Ejecutar los 4 comandos a la vez con logging
    h2.cmd(f'xterm -hold -e "cd {client_path}; python3 ' \
    f'client.py upload -s /tmp/test.png -n uploadsw.png -r SW -H 10.0.0.1 -p 5005 -v 2>&1 | tee {logs_dir}/client_upload_sw.log; bash" &')
    h3.cmd(f'xterm -hold -e "cd {client_path}; python3 ' \
    f'client.py upload -s /tmp/test.png -n uploadgbn.png -r GBN -H 10.0.0.1 -p 5005 -v 2>&1 | tee {logs_dir}/client_upload_gbn.log; bash" &')
    h4.cmd(f'xterm -hold -e "cd {client_path}; python3 ' \
    f'client.py download -d ./downloadsw.png -n test.png -r SW -H 10.0.0.1 -p 5005 -v 2>&1 | tee {logs_dir}/client_download_sw.log; bash" &')
    h5.cmd(f'xterm -hold -e "cd {client_path}; python3 ' \
    f'client.py download -d ./downloadgbn.png -n test.png -r GBN -H 10.0.0.1 -p 5005 -v 2>&1 | tee {logs_dir}/client_download_gbn.log; bash" &')

    print(f"\n=== Red iniciada ===")
    print(f"Capturas de red: {wireshark_dir}/")
    print(f"Logs de aplicación: {logs_dir}/")
    print(f"- server.log: Logs del servidor")
    print(f"- client_upload_sw.log: Logs del cliente upload Stop & Wait")
    print(f"- client_upload_gbn.log: Logs del cliente upload Go Back N")
    print(f"- client_download_sw.log: Logs del cliente download Stop & Wait")
    print(f"- client_download_gbn.log: Logs del cliente download Go Back N")
    print(f"Presiona 'exit' en la CLI de Mininet para terminar\n")
    
    CLI(net)
    
    print("\n=== Terminando red ===")
    h1.cmd("killall xterm")
    h2.cmd("killall xterm")
    h3.cmd("killall xterm")
    h4.cmd("killall xterm")
    h5.cmd("killall xterm")
    
    print(f"Logs guardados en: {logs_dir}/")
    print(f"Capturas guardadas en: {wireshark_dir}/")
    net.stop()


if __name__ == "__main__":
    start_network()