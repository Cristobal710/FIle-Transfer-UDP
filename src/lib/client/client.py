import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from lib.constants import UPLOAD, DOWNLOAD, WINDOW_SIZE_GBN, WINDOW_SIZE_SW, ACK_TIMEOUT_GBN, ACK_TIMEOUT_SW, GO_BACK_N, STOP_AND_WAIT
from lib.protocol.archive import ArchiveSender, ArchiveRecv
from lib.protocol.protocol import handshake, upload, download
from lib.protocol.utils import (
    setup_logging, validate_file_path, validate_protocol, 
    setup_client_socket, create_upload_parser, create_download_parser
)


class FileTransferInterface:
    def __init__(self):
        self.logger = setup_logging('file_transfer')
        self.sock = None
        
    def _setup_socket(self, host, port):
        if self.sock:
            self.sock.close()
            
        self.sock, self.target_addr = setup_client_socket(host, port)
        self.logger.debug(f"Socket bound to {self.sock.getsockname()}")
        self.logger.debug(f"Target server: {host}:{port}")
        
    def upload_file(self, args):
        try:
            self.logger = setup_logging('file_transfer', args.verbose, args.quiet)
            self._setup_socket(args.host, args.port)
            
            source_path = validate_file_path(args.src)
            protocol = validate_protocol(args.protocol)
            
            self.logger.info(f"Starting upload: {source_path} -> {args.name}")
            self.logger.debug(f"Protocol: {protocol}")
            
            # Crear dirección del servidor
            server_addr = (args.host, args.port)
            
            # Handshake
            handshake(self.sock, args.name, UPLOAD, protocol, server_addr)
            
            # Crear archivo sender
            arch = ArchiveSender(source_path)
            end = False
            
            # Usar el protocolo especificado
            if protocol == "SW":
                upload(self.sock, arch, end, WINDOW_SIZE_SW, server_addr, ACK_TIMEOUT_SW)  # GBN con ventana de 1
            elif protocol == "GBN":
                upload(self.sock, arch, end, WINDOW_SIZE_GBN, server_addr, ACK_TIMEOUT_GBN)
                
            self.logger.info("Upload completed successfully")
            
        except Exception as e:
            self.logger.error(f"Upload failed: {e}")
            sys.exit(1)
        finally:
            if self.sock:
                self.sock.close()
                
    def download_file(self, args):
        try:
            self.logger = setup_logging('file_transfer', args.verbose, args.quiet)
            self._setup_socket(args.host, args.port)
            
            protocol = validate_protocol(args.protocol)
            
            self.logger.info(f"Starting download: {args.name} -> {args.dst}")
            self.logger.debug(f"Protocol: {protocol}")
            
            # Crear dirección del servidor
            server_addr = (args.host, args.port)
            
            # Handshake
            handshake(self.sock, args.name, DOWNLOAD, protocol, server_addr)
            
            # Crear archivo receiver
            arch = ArchiveRecv(args.dst)
            end = False
            
            # Usar el protocolo especificado
            if protocol == STOP_AND_WAIT:
                download(self.sock, arch, server_addr, ACK_TIMEOUT_SW)  # GBN con ventana de 1
            elif protocol == GO_BACK_N:
                download(self.sock, arch, server_addr, ACK_TIMEOUT_GBN)
                    
            self.logger.info("Download completed successfully")
            
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            sys.exit(1)
        finally:
            if self.sock:
                self.sock.close()




def main():
    if len(sys.argv) < 2:
        print("File Transfer Client")
        print("Available commands: upload, download")
        print("Use -h for help with each command")
        print()
        
        interface = FileTransferInterface()
        
        while True:
            try:
                command_input = input("Enter command (or 'quit' to exit): ").strip().split()
                
                if not command_input or command_input[0] == 'quit':
                    print("Goodbye!")
                    break
                    
                command = command_input[0]
                
                if command == 'upload':
                    parser = create_upload_parser()
                    try:
                        args = parser.parse_args(command_input[1:])
                        interface.upload_file(args)
                    except SystemExit:
                        pass
                        
                elif command == 'download':
                    parser = create_download_parser()
                    try:
                        args = parser.parse_args(command_input[1:])
                        interface.download_file(args)
                    except SystemExit:
                        pass
                        
                else:
                    print(f"Unknown command: {command}")
                    print("Available commands: upload, download")
                    
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")
    else:
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
