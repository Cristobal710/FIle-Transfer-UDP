import socket
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from constants import *
from protocol.archive import ArchiveSender

if __name__ == "__main__":
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(TUPLA_DIR_CLIENT)
    while True:
        #caso de UPLOAD
        name = input("Nombre del archivo: ")
        path = input("Path: ")
        arch = ArchiveSender(path) 
        sock.sendto(name.encode(), TUPLA_DIR_ENVIO)
        while True:
            pkg = arch.next_pkg()

            if (pkg == None):
                break
            else: 
                sock.sendto(pkg, TUPLA_DIR_ENVIO)
                pkg, addr = sock.recvfrom(1024)
                print(pkg)
                #while pkg == 'NAK':
                    #REENVIAR
