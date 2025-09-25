import socket
from utils import stop_and_wait
from constants import TUPLA_DIR_ENVIO

def handshake(sock: socket, name: str, type: str):
    stop_and_wait(sock, type.encode(), TUPLA_DIR_ENVIO) # send type of conexion to server
    stop_and_wait(sock, name.encode(), TUPLA_DIR_ENVIO) # send file name to server
  
