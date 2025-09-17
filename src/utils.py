import socket
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from constants import *
from protocol.archive import ArchiveSender, ArchiveRecv

def upload_file(sock: socket, end):
    name = input("Nombre del archivo: ")
    path = input("Path: ")
    arch = ArchiveSender(path) 
    
    sock.sendto(UPLOAD.encode(), TUPLA_DIR_ENVIO) #send type of conexion to server
    sock.sendto(name.encode(), TUPLA_DIR_ENVIO) #send file name

    while (not end):
        pkg = arch.next_pkg()
        if (pkg == None):
            pkg = END.encode()
            end = True
        
        sock.sendto(pkg, TUPLA_DIR_ENVIO)
        ack_recv = False
        while (not ack_recv):
            sock.settimeout(0.1) #wait 100 miliseconds to recieve ACK
            try:
                pkg, addr = sock.recvfrom(1024)
                print(pkg.decode())
                ack_recv = True
            except socket.timeout:
                sock.sendto(pkg, TUPLA_DIR_ENVIO)    

def download_file(sock: socket, end):
    name = input("Nombre del archivo: ")
    path = input("Path to save file: ")

    sock.sendto(DOWNLOAD.encode(), TUPLA_DIR_ENVIO) #send type of conexion to server
    sock.sendto(name.encode(), TUPLA_DIR_ENVIO) #send file name to server

    arch = ArchiveRecv(path)
    
    work_done = False
    while (not work_done):
        pkg, addr = sock.recvfrom(1024)
        
        arch.recv_pckg(pkg) 
        
        if (pkg == END.encode()):
            work_done = True

        sock.sendto(ACK.encode(), addr)