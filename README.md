# File-Transfer-UDP

Trabajo Práctico realizado para la Universidad de Buenos Aires, facultad de Ingeniería (FIUBA) donde la finalidad es, utilizando el protocolo de transporte UDP, conseguir una funcionalidad similar al protocolo TCP utilizando diferentes mecanismos para la transferencia de archivos a través de sockets con una arquitectura Cliente-Servidor.

## Estructura del Proyecto

```
src/
lib/                    # Archivos de protocolo, cliente y servidor
  ├── client/           # Código del cliente
  ├── server/           # Código del servidor
  └── protocol/         # Implementación de protocolos UDP
test/                   # Archivos de testing con Mininet
upload                  # Script de upload
download                # Script de download
start-server            # Script para iniciar el servidor
README.md
```

## Instalación de Dependencias

### 1. Instalar dependencias de Python
```bash
pip install -r requirements.txt
```

### 2. Instalar dependencias del sistema (Ubuntu/Debian)
```bash
chmod +x install_dependencies.sh
./install_dependencies.sh
```

### 3. Instalar plugin de Mininet (opcional)
```bash
chmod +x install_plugin.sh
./install_plugin.sh
```

## Uso del Sistema

### Iniciar el Servidor

```bash
# Ayuda del servidor
./start-server -h

# Iniciar servidor con configuración por defecto
./start-server

# Iniciar servidor con configuración personalizada
./start-server -H 192.168.1.100 -p 8080 -s /path/to/storage -v
```

**Parámetros del servidor:**
- `-H, --host`: Dirección IP del servidor (default: 127.0.0.1)
- `-p, --port`: Puerto del servidor (default: 5005)
- `-s, --storage`: Directorio de almacenamiento (default: src/lib/server/storage)
- `-v, --verbose`: Aumentar verbosidad
- `-q, --quiet`: Reducir verbosidad

### Subir Archivos (Upload)

```bash
# Ayuda del upload
./upload -h

# Subir archivo a servidor con determinado protocolo
./upload -H 192.168.1.100 -p 8080 -s test.txt -n uploaded.txt -r SW


./upload -H 192.168.1.100 -p 8080 -s test.txt -n uploaded.txt -r GBN
```

**Parámetros del upload:**
- `-s, --src`: Ruta del archivo fuente (requerido)
- `-n, --name`: Nombre del archivo en el servidor (requerido)
- `-H, --host`: Dirección IP del servidor (default: 127.0.0.1)
- `-p, --port`: Puerto del servidor (default: 5005)
- `-r, --protocol`: Protocolo (SW o GBN, default: SW)
- `-v, --verbose`: Aumentar verbosidad
- `-q, --quiet`: Reducir verbosidad

### Descargar Archivos (Download)

```bash
# Ayuda del download
./download -h

# Descargar archivo de servidor con determinado protocolo
./download -H 192.168.1.100 -p 8080 -n file.txt -d ./downloaded.txt -r SW

./download -H 192.168.1.100 -p 8080 -n file.txt -d ./downloaded.txt -r GBN
```

**Parámetros del download:**
- `-n, --name`: Nombre del archivo a descargar (requerido)
- `-d, --dst`: Ruta de destino (requerido)
- `-H, --host`: Dirección IP del servidor (default: 127.0.0.1)
- `-p, --port`: Puerto del servidor (default: 5005)
- `-r, --protocol`: Protocolo (SW o GBN, default: SW)
- `-v, --verbose`: Aumentar verbosidad
- `-q, --quiet`: Reducir verbosidad

## Testing con Mininet

### Configuración Inicial

1. **Instalar dependencias de Mininet:**
   ```bash
   chmod +x install_dependencies.sh
   ./install_dependencies.sh
   ```

2. **Instalar plugin de Mininet (opcional):**
   ```bash
   chmod +x install_plugin.sh
   ./install_plugin.sh
   ```

### Ejecutar Tests

```bash
# Pararse en el root del proyecto
cd /path/to/FIle-Transfer-UDP

# Ejecutar test de 4 clientes con un comando diferente cada uno
sudo python3 test/mininet_udp_topo.py

# Ejecutar test de upload con Go Back N
sudo python3 test/test_upload_gbn.py

# Ejecutar test de download con Go Back N
sudo python3 test/test_download_gbn.py

# Ejecutar test de upload con Stop and Wait
sudo python3 test/test_upload_sw.py

# Ejecutar test de download con Stop and Wait
sudo python3 test/test_download_sw.py

# Ejecutar 5 terminales de mininet
sudo python3 test/mininet_without_cmds.py 
```

## Protocolos Implementados

### Stop and Wait (SW)
- Ventana de tamaño 1
- Timeout: 0.05s
- Tiempo aproximado: ~1 minuto para archivos grandes

### Go Back N (GBN)
- Ventana de tamaño 10
- Timeout: 0.05s
- Tiempo aproximado: ~14 segundos para archivos grandes

## Plugin de Wireshark

El plugin `udp_file_transfer.lua` permite visualizar el tráfico UDP en Wireshark con información específica del protocolo implementado.

### Instalación del Plugin

1. **Descargar el plugin:**
   ```bash
   # El plugin ya está incluido en el proyecto
   ls udp_file_transfer.lua
   ```

2. **Instalar en Wireshark:**
   ```bash
   # Copiar a directorio de plugins de Wireshark
   cp udp_file_transfer.lua ~/.local/lib/wireshark/plugins/
   
   # O usar el script de instalación
   chmod +x install_plugin.sh
   ./install_plugin.sh
   ```

3. **Reiniciar Wireshark** para cargar el plugin

### Uso del Plugin

1. Capturar tráfico con tcpdump durante los tests
2. Abrir el archivo .pcap en Wireshark
3. El plugin mostrará información detallada de los paquetes UDP del protocolo

## Archivos de Log y Capturas

Los tests generan automáticamente:
- **Logs**: `logs/server.log`, `logs/client_*.log`
- **Capturas**: `wireshark_files/h1_capture.pcap`, `wireshark_files/h2_capture.pcap`

## Solución de Problemas

### Error de permisos
```bash
# Hacer ejecutables los scripts
chmod +x upload download start-server
```

### Error de dependencias
```bash
# Reinstalar dependencias
pip install -r requirements.txt
./install_dependencies.sh
```

### Error de Mininet
```bash
# Limpiar namespaces de Mininet
sudo mn -c
```