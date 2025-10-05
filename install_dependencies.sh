#!/bin/bash

echo "🔧 Instalando dependencias para pruebas con Mininet..."

# Verificar si estamos en Ubuntu/Debian
if command -v apt-get &> /dev/null; then
    echo "📦 Instalando paquetes del sistema..."
    sudo apt-get update
    sudo apt-get install -y mininet xterm tcpdump wireshark-common
    
    echo "🐍 Instalando dependencias de Python..."
    pip3 install mininet
    
    echo "✅ Dependencias instaladas correctamente"
    echo ""
    echo "🚀 Para ejecutar las pruebas:"
    echo "   sudo python3 run_mininet_test.py"
    echo ""
    echo "📊 Para analizar las capturas de red:"
    echo "   wireshark wireshark_files/h1_capture.pcap"
    
elif command -v yum &> /dev/null; then
    echo "📦 Instalando paquetes del sistema (CentOS/RHEL)..."
    sudo yum install -y mininet xterm tcpdump wireshark
    
    echo "🐍 Instalando dependencias de Python..."
    pip3 install mininet
    
    echo "✅ Dependencias instaladas correctamente"
    
else
    echo "❌ Sistema operativo no soportado"
    echo "   Por favor instala manualmente:"
    echo "   - mininet"
    echo "   - xterm"
    echo "   - tcpdump"
    echo "   - wireshark"
    echo "   - python3-mininet"
    exit 1
fi
