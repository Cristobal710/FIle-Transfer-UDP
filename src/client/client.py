import socket
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from constants import *
from utils import *

if __name__ == "__main__":
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(TUPLA_DIR_CLIENT)
    end = False
    #while (not end):
    upload_file(sock, end)    
    sock.close()
