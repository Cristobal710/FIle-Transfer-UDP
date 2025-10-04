from mininet.net import Mininet
from mininet.cli import CLI
from mininet.node import Controller, OVSKernelSwitch
from mininet.link import TCLink

def start_network():
    net = Mininet(controller=Controller, switch=OVSKernelSwitch, link=TCLink)

    # Add controller with explicit executable
    net.addController("c0", controller=Controller, command="ovs-testcontroller")

    # Add hosts and switch
    h1 = net.addHost("h1", ip="10.0.0.1", cwd="src/server")
    h2 = net.addHost("h2", ip="10.0.0.2", cwd="src/client")
    h3 = net.addHost("h3", ip="10.0.0.3", cwd="src/client")
    h4 = net.addHost("h4", ip="10.0.0.4", cwd="src/client")
    h5 = net.addHost("h5", ip="10.0.0.5", cwd="src/client")
    s1 = net.addSwitch("s1")

    net.addLink(h1, s1, loss= 10)
    net.addLink(h2, s1)
    net.addLink(h3, s1)
    net.addLink(h4, s1)
    net.addLink(h5, s1)
    net.start()

    # Start tcpdump on server (h1)
    tcpdump_h1 = h1.popen("tcpdump -i h1-eth0 udp -w wireshark_files/h1_capture.pcap")

    # Start tcpdump on client (h2)
    tcpdump_h2 = h2.popen("tcpdump -i h2-eth0 udp -w wireshark_files/h2_capture.pcap")

    # Start tcpdump on client (h3)
    tcpdump_h3 = h3.popen("tcpdump -i h3-eth0 udp -w wireshark_files/h3_capture.pcap")
    # Start tcpdump on client (h4)
    tcpdump_h4 = h4.popen("tcpdump -i h4-eth0 udp -w wireshark_files/h4_capture.pcap")
    # Start tcpdump on client (h5)
    tcpdump_h5 = h5.popen("tcpdump -i h5-eth0 udp -w wireshark_files/h5_capture.pcap")

    h1.cmd('xterm -hold -e "cd src/server; python3 server.py start-server -H 10.0.0.1 -p 5005; bash" &')
    h2.cmd('xterm -hold -e "cd src/client; python3 ' \
    'client.py upload -s ./test.png -n uploadsw.png -r SW -H 10.0.0.1 -p 5005 -v; bash" &')
    h3.cmd('xterm -hold -e "cd src/client; python3 ' \
    'client.py upload -s ./test.png -n uploadgbn.png -r GBN -H 10.0.0.1 -p 5005 -v; bash" &')
    h4.cmd('xterm -hold -e "cd src/client; python3 ' \
    'client.py download -d ./downloadsw.png -n test.png -r SW -H 10.0.0.1 -p 5005 -v; bash" &')
    h5.cmd('xterm -hold -e "cd src/client; python3 ' \
    'client.py download -d ./downloadgbn.png -n test.png -r GBN -H 10.0.0.1 -p 5005 -v; bash" &')

    CLI(net)
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
    net.stop()


if __name__ == "__main__":
    start_network()
