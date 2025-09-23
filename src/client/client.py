import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from interface import FileTransferInterface, create_upload_parser, create_download_parser

if __name__ == "__main__":
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
