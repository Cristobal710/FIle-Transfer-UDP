#!/usr/bin/env python3
"""
Script de prueba para verificar la concurrencia del servidor
con múltiples clientes simultáneos.
"""

import subprocess
import time
import threading
import os
import sys

def run_client_download(client_id, filename, protocol="SW"):
    """Ejecuta un cliente de descarga"""
    try:
        cmd = [
            sys.executable, 
            "src/client/client.py", 
            "download", 
            "--name", filename,
            "--dst", f"downloaded_{client_id}_{filename}",
            "--protocol", protocol,
            "--host", "127.0.0.1",
            "--port", "5005"
        ]
        
        print(f"[Cliente {client_id}] Iniciando descarga de {filename} con {protocol}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print(f"[Cliente {client_id}] ✅ Descarga completada exitosamente")
            return True
        else:
            print(f"[Cliente {client_id}] ❌ Error en descarga: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"[Cliente {client_id}] ⏰ Timeout en descarga")
        return False
    except Exception as e:
        print(f"[Cliente {client_id}] ❌ Error: {e}")
        return False

def run_client_upload(client_id, filename, protocol="SW"):
    """Ejecuta un cliente de subida"""
    try:
        # Crear archivo de prueba
        test_file = f"test_upload_{client_id}.txt"
        with open(test_file, 'w') as f:
            f.write(f"Contenido de prueba del cliente {client_id}\n" * 100)
        
        cmd = [
            sys.executable, 
            "src/client/client.py", 
            "upload", 
            "--src", test_file,
            "--name", f"uploaded_{client_id}_{filename}",
            "--protocol", protocol,
            "--host", "127.0.0.1",
            "--port", "5005"
        ]
        
        print(f"[Cliente {client_id}] Iniciando subida de {test_file} con {protocol}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        # Limpiar archivo temporal
        if os.path.exists(test_file):
            os.remove(test_file)
        
        if result.returncode == 0:
            print(f"[Cliente {client_id}] ✅ Subida completada exitosamente")
            return True
        else:
            print(f"[Cliente {client_id}] ❌ Error en subida: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"[Cliente {client_id}] ⏰ Timeout en subida")
        return False
    except Exception as e:
        print(f"[Cliente {client_id}] ❌ Error: {e}")
        return False

def test_concurrent_downloads():
    """Prueba descargas concurrentes"""
    print("\n🔄 Probando descargas concurrentes...")
    
    # Crear archivo de prueba en el servidor
    test_file = "src/server/storage/test_concurrent.txt"
    with open(test_file, 'w') as f:
        f.write("Archivo de prueba para concurrencia\n" * 1000)
    
    threads = []
    results = []
    
    # Crear 3 clientes concurrentes
    for i in range(3):
        def client_wrapper(client_id):
            result = run_client_download(client_id, "test_concurrent.txt", "SW")
            results.append((client_id, result))
        
        t = threading.Thread(target=client_wrapper, args=(i+1,))
        threads.append(t)
        t.start()
    
    # Esperar a que terminen todos
    for t in threads:
        t.join()
    
    # Verificar resultados
    successful = sum(1 for _, success in results if success)
    print(f"📊 Resultados: {successful}/3 descargas exitosas")
    
    # Limpiar archivo de prueba
    if os.path.exists(test_file):
        os.remove(test_file)
    
    return successful == 3

def test_mixed_operations():
    """Prueba operaciones mixtas (upload y download)"""
    print("\n🔄 Probando operaciones mixtas...")
    
    threads = []
    results = []
    
    # Crear archivo de prueba
    test_file = "src/server/storage/test_mixed.txt"
    with open(test_file, 'w') as f:
        f.write("Archivo de prueba para operaciones mixtas\n" * 500)
    
    # 2 descargas y 2 subidas concurrentes
    operations = [
        ("download", 1, "test_mixed.txt"),
        ("upload", 2, "mixed_upload_1.txt"),
        ("download", 3, "test_mixed.txt"),
        ("upload", 4, "mixed_upload_2.txt")
    ]
    
    for op_type, client_id, filename in operations:
        def client_wrapper():
            if op_type == "download":
                result = run_client_download(client_id, filename, "SW")
            else:
                result = run_client_upload(client_id, filename, "SW")
            results.append((client_id, op_type, result))
        
        t = threading.Thread(target=client_wrapper)
        threads.append(t)
        t.start()
    
    # Esperar a que terminen todos
    for t in threads:
        t.join()
    
    # Verificar resultados
    successful = sum(1 for _, _, success in results if success)
    print(f"📊 Resultados: {successful}/4 operaciones exitosas")
    
    # Limpiar archivos de prueba
    for file in [test_file, "src/server/storage/mixed_upload_1.txt", "src/server/storage/mixed_upload_2.txt"]:
        if os.path.exists(file):
            os.remove(file)
    
    return successful == 4

def main():
    print("🚀 Iniciando pruebas de concurrencia del servidor UDP")
    print("=" * 60)
    
    # Verificar que el servidor esté corriendo
    print("⚠️  Asegúrate de que el servidor esté corriendo en otra terminal:")
    print("   python src/server/server.py start-server")
    print()
    
    input("Presiona Enter cuando el servidor esté listo...")
    
    # Ejecutar pruebas
    test1_passed = test_concurrent_downloads()
    test2_passed = test_mixed_operations()
    
    print("\n" + "=" * 60)
    print("📋 RESUMEN DE PRUEBAS:")
    print(f"   Descargas concurrentes: {'✅ PASÓ' if test1_passed else '❌ FALLÓ'}")
    print(f"   Operaciones mixtas: {'✅ PASÓ' if test2_passed else '❌ FALLÓ'}")
    
    if test1_passed and test2_passed:
        print("\n🎉 ¡Todas las pruebas pasaron! La concurrencia funciona correctamente.")
    else:
        print("\n⚠️  Algunas pruebas fallaron. Revisa los logs del servidor.")
    
    print("\n💡 Consejo: Revisa los logs del servidor para ver el enrutamiento de paquetes")

if __name__ == "__main__":
    main()
