"""
Utilidades compartidas para el cliente y servidor
"""
import argparse
import logging
import os
import socket
import sys

from src.lib.constants import STOP_AND_WAIT, GO_BACK_N


def find_free_port():
    """
    Encuentra el primer puerto libre disponible
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def setup_logging(name, verbose=False, quiet=False):
    """
    Configura el sistema de logging para el cliente o servidor
    """
    if verbose and quiet:
        raise argparse.ArgumentTypeError("Cannot specify both -v and -q")
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    if verbose:
        logger.setLevel(logging.DEBUG)
    elif quiet:
        logger.setLevel(logging.WARNING)
    else:
        logger.setLevel(logging.INFO)
    
    return logger


def validate_file_path(filepath):
    """
    Valida que el archivo existe y es un archivo válido
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    if not os.path.isfile(filepath):
        raise ValueError(f"Path is not a file: {filepath}")
    return filepath


def validate_protocol(protocol):
    """
    Valida que el protocolo es válido
    """
    valid_protocols = [STOP_AND_WAIT, GO_BACK_N]
    if protocol not in valid_protocols:
        raise ValueError(f"Invalid protocol. Must be one of: {valid_protocols}")
    return protocol


def setup_client_socket(host, port):
    """
    Configura el socket del cliente
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Encontrar el primer puerto libre disponible
    client_port = find_free_port()
    
    if host == "127.0.0.1" or host == "localhost":
        client_ip = "127.0.0.1"
    else:
        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            temp_sock.connect((host, port))
            client_ip = temp_sock.getsockname()[0]
        except:
            client_ip = "0.0.0.0"
        finally:
            temp_sock.close()
    
    sock.bind((client_ip, client_port))
    return sock, (host, port)


def create_common_parser_args(parser):
    """
    Agrega argumentos comunes a los parsers
    """
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='increase output verbosity'
    )
    
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='decrease output verbosity'
    )
    
    parser.add_argument(
        '-H', '--host',
        default='127.0.0.1',
        help='server IP address'
    )
    
    parser.add_argument(
        '-p', '--port',
        type=int,
        default=5005,
        help='server port'
    )
    
    parser.add_argument(
        '-r', '--protocol',
        choices=[STOP_AND_WAIT, GO_BACK_N],
        default=STOP_AND_WAIT,
        help='error recovery protocol'
    )
    
    return parser


def create_upload_parser():
    """
    Crea el parser para comandos de upload
    """
    parser = argparse.ArgumentParser(
        prog='upload',
        description='Send a file to the server to be saved with the assigned name'
    )
    
    parser = create_common_parser_args(parser)
    
    parser.add_argument(
        '-s', '--src',
        required=True,
        help='source file path'
    )
    
    parser.add_argument(
        '-n', '--name',
        required=True,
        help='file name'
    )
    
    return parser


def create_download_parser():
    """
    Crea el parser para comandos de download
    """
    parser = argparse.ArgumentParser(
        prog='download',
        description='Download a specified file from the server'
    )
    
    parser = create_common_parser_args(parser)
    
    parser.add_argument(
        '-n', '--name',
        required=True,
        help='file name to download'
    )
    
    parser.add_argument(
        '-d', '--dst',
        dest='dst',
        required=True,
        help='destination file path'
    )
    
    return parser


def create_server_parser():
    """
    Crea el parser para comandos del servidor
    """
    parser = argparse.ArgumentParser(
        prog='start-server',
        description='Start the file transfer server'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='increase output verbosity'
    )
    
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='decrease output verbosity'
    )
    
    parser.add_argument(
        '-H', '--host',
        default='127.0.0.1',
        help='server IP address to bind to'
    )
    
    parser.add_argument(
        '-p', '--port',
        type=int,
        default=5005,
        help='server port to bind to'
    )
    
    parser.add_argument(
        '-s', '--storage',
        default='src/server/storage',
        help='directory to store uploaded files'
    )
    
    return parser
