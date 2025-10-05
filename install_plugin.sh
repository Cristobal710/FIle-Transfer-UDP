#!/bin/bash

# Script para instalar el plugin de Wireshark UDP File Transfer
# Detecta automáticamente el directorio de plugins de Wireshark

echo "=== Instalador del Plugin UDP File Transfer para Wireshark ==="

# Función para encontrar el directorio de plugins
find_plugin_directory() {
    local possible_dirs=(
        "$HOME/.local/lib/wireshark/plugins"
        "$HOME/.wireshark/plugins" 
        "/usr/lib/x86_64-linux-gnu/wireshark/plugins"
        "/usr/local/lib/wireshark/plugins"
        "/opt/wireshark/lib/wireshark/plugins"
    )
    
    for dir in "${possible_dirs[@]}"; do
        if [ -d "$dir" ] || [ -d "$(dirname "$dir")" ]; then
            echo "$dir"
            return 0
        fi
    done
    
    # Si no encontramos ninguno, usar el directorio por defecto del usuario
    echo "$HOME/.local/lib/wireshark/plugins"
}

# Encontrar directorio de plugins
PLUGIN_DIR=$(find_plugin_directory)
echo "Directorio de plugins detectado: $PLUGIN_DIR"

# Crear el directorio si no existe
if [ ! -d "$PLUGIN_DIR" ]; then
    echo "Creando directorio de plugins: $PLUGIN_DIR"
    mkdir -p "$PLUGIN_DIR"
fi

# Copiar el plugin
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_FILE="$SCRIPT_DIR/udp_file_transfer.lua"

if [ ! -f "$PLUGIN_FILE" ]; then
    echo "Error: No se encuentra el archivo del plugin: $PLUGIN_FILE"
    exit 1
fi

echo "Copiando plugin a: $PLUGIN_DIR/"
cp "$PLUGIN_FILE" "$PLUGIN_DIR/"

if [ $? -eq 0 ]; then
    echo "✅ Plugin instalado correctamente!"
    echo ""
    echo "📋 Instrucciones para usar el plugin:"
    echo "1. Reinicia Wireshark si está abierto"
    echo "2. Inicia la captura de paquetes (interfaz loopback para localhost)"
    echo "3. Ejecuta tu aplicación de transferencia de archivos"
    echo "4. Los paquetes aparecerán como 'UDP File Transfer Protocol'"
    echo ""
    echo "🔍 Filtros útiles en Wireshark:"
    echo "   - udpft                    (todos los paquetes del protocolo)"
    echo "   - udpft.flag_end == 1      (solo paquetes END)"
    echo "   - udpft.seq_num == 0       (solo paquetes con seq_num = 0)"
    echo "   - udpft.ack_num            (solo paquetes ACK)"
    echo "   - udp.port == 5005         (solo tráfico del servidor)"
    echo ""
    echo "🎯 Verificación:"
    echo "Ve a: Help -> About Wireshark -> Plugins"
    echo "Deberías ver 'udp_file_transfer.lua' en la lista"
else
    echo "❌ Error al copiar el plugin"
    exit 1
fi
