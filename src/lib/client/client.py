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
    
    # ✅ IMPORTANTE: Este método debe estar al mismo nivel de indentación que __init__
    def _setup_socket(self, host, port):
        if self.sock:
            self.sock.close()
            
        self.sock, self.target_addr = setup_client_socket(host, port)
        self.logger.debug(f"Socket bound to {self.sock.getsockname()}")
        self.logger.debug(f"Target server: {host}:{port}")
    
    # ✅ Este también debe estar al mismo nivel
    def upload_file(self, args):
        try:
            self.logger = setup_logging('file_transfer', args.verbose, args.quiet)
            self._setup_socket(args.host, args.port)  # <-- Aquí se llama
            
            source_path = validate_file_path(args.src)
            protocol = validate_protocol(args.protocol)
            
            self.logger.info(f"Starting upload: {source_path} -> {args.name}")
            self.logger.debug(f"Protocol: {protocol}")
            
            server_addr = (args.host, args.port)
            
            handshake(self.sock, args.name, UPLOAD, protocol, server_addr, args.verbose, args.quiet)
            
            arch = ArchiveSender(source_path)
            end = False
            
            if protocol == "SW":
                upload(self.sock, arch, end, WINDOW_SIZE_SW, server_addr, ACK_TIMEOUT_SW, args.verbose, args.quiet)
            elif protocol == "GBN":
                upload(self.sock, arch, end, WINDOW_SIZE_GBN, server_addr, ACK_TIMEOUT_GBN, args.verbose, args.quiet)
                
            self.logger.info("Upload completed successfully")
            
        except Exception as e:
            self.logger.error(f"Upload failed: {e}")
            sys.exit(1)
        finally:
            if self.sock:
                self.sock.close()
    
    # ✅ Este también debe estar al mismo nivel            
    def download_file(self, args):
        try:
            self.logger = setup_logging('file_transfer', args.verbose, args.quiet)
            self._setup_socket(args.host, args.port)  # <-- Aquí se llama
            
            protocol = validate_protocol(args.protocol)
            
            self.logger.info(f"Starting download: {args.name} -> {args.dst}")
            self.logger.debug(f"Protocol: {protocol}")
            
            server_addr = (args.host, args.port)
            
            handshake(self.sock, args.name, DOWNLOAD, protocol, server_addr, args.verbose, args.quiet)
            
            arch = ArchiveRecv(args.dst)
            end = False
            
            if protocol == STOP_AND_WAIT:
                download(self.sock, arch, server_addr, ACK_TIMEOUT_SW, args.verbose, args.quiet)
            elif protocol == GO_BACK_N:
                download(self.sock, arch, server_addr, ACK_TIMEOUT_GBN, args.verbose, args.quiet)
                    
            self.logger.info("Download completed successfully")
            
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            sys.exit(1)
        finally:
            if self.sock:
                self.sock.close()


def main():
    # Logger para el modo interactivo
    interactive_logger = setup_logging('file_transfer.interactive')
    
    if len(sys.argv) < 2:
        interactive_logger.info("File Transfer Client")
        interactive_logger.info("Available commands: upload, download")
        interactive_logger.info("Use -h for help with each command")
        interactive_logger.info("")
        
        interface = FileTransferInterface()
        
        while True:
            try:
                command_input = input("Enter command (or 'quit' to exit): ").strip().split()
                
                if not command_input or command_input[0] == 'quit':
                    interactive_logger.info("Goodbye!")
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
                    interactive_logger.warning(f"Unknown command: {command}")
                    interactive_logger.info("Available commands: upload, download")
                    
            except KeyboardInterrupt:
                interactive_logger.info("\nGoodbye!")
                break
            except Exception as e:
                interactive_logger.error(f"Error: {e}")
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
            interface.logger.error(f"Unknown command: {command}")
            interface.logger.info("Available commands: upload, download")
            sys.exit(1)


if __name__ == "__main__":
    main()