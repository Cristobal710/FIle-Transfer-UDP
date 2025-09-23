import argparse
import socket
import sys
import os
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))
from constants import (
    UPLOAD, DOWNLOAD, TUPLA_DIR_ENVIO, END, ACK, ACK_TIMEOUT, 
    PROTOCOLO, STOP_AND_WAIT, GO_BACK_N, SIZE_PKG
)
from protocol.archive import ArchiveSender, ArchiveRecv
from utils import stop_and_wait


class FileTransferInterface:
    def __init__(self):
        self.logger = self._setup_logging()
        self.sock = None
        
    def _setup_logging(self):
        logger = logging.getLogger('file_transfer')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(levelname)s: %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
        
    def _set_verbosity(self, verbose, quiet):
        if verbose and quiet:
            raise argparse.ArgumentTypeError("Cannot specify both -v and -q")
            
        if verbose:
            self.logger.setLevel(logging.DEBUG)
        elif quiet:
            self.logger.setLevel(logging.WARNING)
        else:
            self.logger.setLevel(logging.INFO)
            
    def _setup_socket(self, host, port):
        if self.sock:
            self.sock.close()
            
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        client_port = 5006
        if host == "127.0.0.1" or host == "localhost":
            client_ip = "127.0.0.1"
        else:
            client_ip = "10.0.0.2"
            
        self.sock.bind((client_ip, client_port))
        self.logger.debug(f"Socket bound to {client_ip}:{client_port}")
        
        global TUPLA_DIR_ENVIO
        TUPLA_DIR_ENVIO = (host, port)
        self.logger.debug(f"Target server: {host}:{port}")
        
    def _validate_file_path(self, filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Source file not found: {filepath}")
        if not os.path.isfile(filepath):
            raise ValueError(f"Path is not a file: {filepath}")
        return filepath
        
    def _validate_protocol(self, protocol):
        valid_protocols = [STOP_AND_WAIT, GO_BACK_N]
        if protocol not in valid_protocols:
            raise ValueError(f"Invalid protocol. Must be one of: {valid_protocols}")
        return protocol
        
    def upload_file(self, args):
        try:
            self._set_verbosity(args.verbose, args.quiet)
            self._setup_socket(args.host, args.port)
            
            source_path = self._validate_file_path(args.src)
            protocol = self._validate_protocol(args.protocol)
            
            self.logger.info(f"Starting upload: {source_path} -> {args.name}")
            self.logger.debug(f"Protocol: {protocol}")
            
            stop_and_wait(self.sock, UPLOAD.encode(), TUPLA_DIR_ENVIO)
            stop_and_wait(self.sock, args.name.encode(), TUPLA_DIR_ENVIO)
            
            arch = ArchiveSender(source_path)
            end = False
            seq_num = 0
            
            while not end:
                pkg = arch.next_pkg(seq_num)
                if pkg is None:
                    pkg = END.encode()
                    end = True
                    
                self.logger.debug(f"Sending packet seq={seq_num}")
                stop_and_wait(self.sock, pkg, TUPLA_DIR_ENVIO)
                seq_num = 1 - seq_num
                
            self.logger.info("Upload completed successfully")
            
        except Exception as e:
            self.logger.error(f"Upload failed: {e}")
            sys.exit(1)
        finally:
            if self.sock:
                self.sock.close()
                
    def download_file(self, args):
        try:
            self._set_verbosity(args.verbose, args.quiet)
            self._setup_socket(args.host, args.port)
            
            protocol = self._validate_protocol(args.protocol)
            
            self.logger.info(f"Starting download: {args.name} -> {args.dest}")
            self.logger.debug(f"Protocol: {protocol}")
            
            stop_and_wait(self.sock, DOWNLOAD.encode(), TUPLA_DIR_ENVIO)
            stop_and_wait(self.sock, args.name.encode(), TUPLA_DIR_ENVIO)
            
            arch = ArchiveRecv(args.dest)
            seq_expected = 0
            work_done = False
            
            while not work_done:
                pkg, addr = self.sock.recvfrom(1024)
                
                if pkg == END.encode():
                    self.logger.info("Transfer completed")
                    work_done = True
                    self.sock.sendto(f"ACK{seq_expected}".encode(), addr)
                    arch.archivo.close()
                    break
                    
                seq_num, data_len, data = arch.recv_pckg(pkg)
                self.logger.debug(f"Received seq={seq_num}, expected={seq_expected}, len={data_len}")
                
                if seq_num == seq_expected:
                    arch.archivo.write(data)
                    arch.archivo.flush()
                    self.sock.sendto(f"ACK{seq_num}".encode(), addr)
                    self.logger.debug(f"Sending ACK{seq_num}")
                    seq_expected = 1 - seq_expected
                else:
                    self.sock.sendto(f"ACK{1 - seq_expected}".encode(), addr)
                    self.logger.debug(f"Duplicate packet, resending ACK{1 - seq_expected}")
                    
            self.logger.info("Download completed successfully")
            
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            sys.exit(1)
        finally:
            if self.sock:
                self.sock.close()


def create_upload_parser():
    parser = argparse.ArgumentParser(
        prog='upload',
        description='Send a file to the server to be saved with the assigned name'
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
        help='server IP address'
    )
    
    parser.add_argument(
        '-p', '--port',
        type=int,
        default=5005,
        help='server port'
    )
    
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
    
    parser.add_argument(
        '-r', '--protocol',
        choices=[STOP_AND_WAIT, GO_BACK_N],
        default=STOP_AND_WAIT,
        help='error recovery protocol'
    )
    
    return parser


def create_download_parser():
    parser = argparse.ArgumentParser(
        prog='download',
        description='Download a specified file from the server'
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
        help='server IP address'
    )
    
    parser.add_argument(
        '-p', '--port',
        type=int,
        default=5005,
        help='server port'
    )
    
    parser.add_argument(
        '-n', '--name',
        required=True,
        help='file name to download'
    )
    
    parser.add_argument(
        '-d', '--dest',
        required=True,
        help='destination file path'
    )
    
    parser.add_argument(
        '-r', '--protocol',
        choices=[STOP_AND_WAIT, GO_BACK_N],
        default=STOP_AND_WAIT,
        help='error recovery protocol'
    )
    
    return parser


def main():
    if len(sys.argv) < 2:
        print("Usage: python interface.py <command> [options]")
        print("Commands: upload, download")
        sys.exit(1)
        
    command = sys.argv[1]
    sys.argv = sys.argv[1:]
    
    interface = FileTransferInterface()
    
    if command == 'upload':
        parser = create_upload_parser()
        args = parser.parse_args()
        interface.upload_file(args)
        
    elif command == 'download':
        parser = create_download_parser()
        args = parser.parse_args()
        interface.download_file(args)
        
    else:
        print(f"Unknown command: {command}")
        print("Available commands: upload, download")
        sys.exit(1)


if __name__ == "__main__":
    main()
