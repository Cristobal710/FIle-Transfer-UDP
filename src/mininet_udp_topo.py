from mininet.net import Mininet
from mininet.cli import CLI
from mininet.node import Controller, OVSKernelSwitch


def start_network():
    net = Mininet(controller=Controller, switch=OVSKernelSwitch)

    # Add controller with explicit executable
    net.addController("c0", controller=Controller, command="ovs-testcontroller")

    # Add hosts and switch
    h1 = net.addHost("h1", ip="10.0.0.1", cwd="src/server")
    h2 = net.addHost("h2", ip="10.0.0.2", cwd="src/client")
    s1 = net.addSwitch("s1")

    net.addLink(h1, s1)
    net.addLink(h2, s1)

    net.start()

    # Start tcpdump on server (h1)
    tcpdump_h1 = h1.popen("tcpdump -i h1-eth0 udp -w wireshark_files/h1_capture.pcap")

    # Start tcpdump on client (h2)
    tcpdump_h2 = h2.popen("tcpdump -i h2-eth0 udp -w wireshark_files/h2_capture.pcap")

    h1.cmd('xterm -hold -e "cd src/server; python3 server.py; bash" &')
    h2.cmd('xterm -hold -e "cd src/client; python3 client.py; bash" &')

    CLI(net)
    h1.cmd("killall xterm")
    h2.cmd("killall xterm")
    tcpdump_h1.terminate()
    tcpdump_h2.terminate()
    net.stop()


if __name__ == "__main__":
    start_network()
