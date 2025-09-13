import socket
import threading
import queue
UDP_IP = "127.0.0.1"
UDP_PORT = 5005
TUPLA_DIR = (UDP_IP, UDP_PORT)


def manage_client(channel: queue.Queue):
    print("mandando desde uno nuevo")
    while True:
        msg = channel.get(block=True)
        print(msg)
        if (msg == "END"):
            break
    print("Me cerre")

        



class Server:
    def __init__(self, udp_ip, udp_port, path):
        self.udp_ip = udp_ip
        self.udp_port = udp_port
        #self.dir_path = path
        self.clients = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((udp_ip, udp_port))

    #Escucha mensajes. Si recibe un nuevo cliente lo agrega al mapa de clientes sino deriva el mensaje a su thread.
    def listen(self):
        while True:
            msg, addr = self.sock.recvfrom(1024) 
            msg = msg.decode()
            if (addr in self.clients): 
                self.clients[addr][0].put(msg) 
                if (msg == "END"):
                    self.clients[addr][1].join()
                    del self.clients[addr]
            else:
                self.start_client(msg, addr)

    #Inicializa un thread que maneja un cliente, enviandole un canal para comunicacion entre thread y proceso principal
    def start_client(self, msg, addr):
        chan = queue.Queue()
        t = threading.Thread(target = manage_client, args = (chan, ))
        t.start()
        self.clients[addr] = [chan, t]
        chan.put(msg)
    


if __name__ == "__main__":

    server = Server(UDP_IP, UDP_PORT, "hola")
    server.listen()