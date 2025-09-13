import socket
UDP_IP = "127.0.0.1"
UDP_PORT = 5006
MESSAGE = "Hello, World!"
TUPLA_DIR = (UDP_IP, UDP_PORT)
TUPLA_DIR_ENVIO = (UDP_IP, 5005)


if __name__ == "__main__":
    print("UDP target IP: %s" % UDP_IP)
    print("UDP target port: %s" % UDP_PORT)
    print("message: %s" % MESSAGE)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(TUPLA_DIR)
    while True:
        msg = input()
        if (msg == "n"):
            break
        sock.sendto(msg.encode(), TUPLA_DIR_ENVIO)
        
