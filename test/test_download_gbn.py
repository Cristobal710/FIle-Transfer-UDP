from mininet.net import Mininet
from mininet.cli import CLI
from mininet.node import Controller, OVSKernelSwitch
from mininet.link import TCLink


def start_network():
    net = Mininet(controller=Controller, switch=OVSKernelSwitch, link=TCLink)

    # Add controller with explicit executable
    net.addController(
        "c0", controller=Controller, command="ovs-testcontroller"
    )

    # Add hosts and switch (usar rutas absolutas)
    import os
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    h1 = net.addHost("h1", ip="10.0.0.1")
    h2 = net.addHost("h2", ip="10.0.0.2")
    s1 = net.addSwitch("s1")

    net.addLink(h1, s1, loss=10)
    net.addLink(h2, s1)

    net.start()

    # Crear directorio para archivos de wireshark si no existe
    wireshark_dir = os.path.join(base_path, "wireshark_files")
    if not os.path.exists(wireshark_dir):
        os.makedirs(wireshark_dir)

    # Start tcpdump on server (h1)
    h1.popen(f"tcpdump -i h1-eth0 udp -w {wireshark_dir}/h1_capture.pcap")

    # Start tcpdump on client (h2)
    h2.popen(f"tcpdump -i h2-eth0 udp -w {wireshark_dir}/h2_capture.pcap")

    # Usar rutas absolutas para los comandos
    server_path = os.path.join(base_path, "src", "lib", "server")
    client_path = os.path.join(base_path, "src", "lib", "client")
    # Copiar archivo de prueba al servidor
    test_file_path = os.path.join(base_path, "test.png")
    h1.cmd(f'cp {test_file_path} {server_path}/storage/test.png')
    # Verificar que el archivo se copió al servidor
    h1.cmd(f'ls -la {server_path}/storage/test.png')
    # Levantar servidor primero
    h1.cmd(
        f'xterm -hold -e "cd {server_path}; python3 server.py '
        f'start-server -H 10.0.0.1 -p 5000; bash" &'
    )

    # Esperar un poco para que el servidor se inicie
    import time
    time.sleep(2)
    # Ejecutar comando de download
    h2.cmd(
        f'xterm -hold -e "cd {client_path}; python3 client.py '
        f'download -d ./downloadgbn.png -n test.png -r GBN '
        f'-H 10.0.0.1 -p 5000 -v; bash" &'
    )

    CLI(net)
    h1.cmd("killall xterm")
    h2.cmd("killall xterm")
    net.stop()


if __name__ == "__main__":
    start_network()
