import os
import pyshark
import pandas as pd
import matplotlib.pyplot as plt
import csv

# === CONFIGURACIÓN ===
pcap_dir = os.path.join(os.getcwd(), "wireshark_files")
metricas_dir = os.path.join(os.getcwd(), "metricas")
os.makedirs(metricas_dir, exist_ok=True)
out_csv = os.path.join(metricas_dir, "metricas_pcap.csv")

# === MAPEO DE HOSTS A PROTOCOLOS ===
roles = {
    "h2": ("upload", "SW"),
    "h3": ("upload", "GBN"),
    "h4": ("download", "SW"),
    "h5": ("download", "GBN")
}

resultados = []

# === PROCESAR CADA ARCHIVO PCAP ===
for fname in sorted(os.listdir(pcap_dir)):
    if not fname.endswith(".pcap"):
        continue

    path = os.path.join(pcap_dir, fname)
    print(f"Analizando {fname}...")

    # Detectar el host a partir del nombre del archivo
    host_id = None
    for h in roles:
        if fname.startswith(h):
            host_id = h
            break

    if not host_id:
        print(f"  [!] No se reconoce el host para {fname}, se omite.")
        continue

    # Captura con PyShark (solo paquetes UDP de tu puerto o protocolo)
    with pyshark.FileCapture(
        path, display_filter="udp && udp.port==5005"
    ) as pcap:
        tiempos = []
        bytes_totales = 5242880

        for pkt in pcap:
            # Filtrar solo tus paquetes personalizados (UDPFT_CUSTOM)
            if "UDPFT" not in pkt.highest_layer:
                continue
            tiempos.append(float(pkt.sniff_timestamp))

        if tiempos:
            duracion = max(tiempos) - min(tiempos)
        else:
            duracion = 0

    throughput = (bytes_totales / 1024 / duracion) if duracion > 0 else 0

    role, protocolo = roles[host_id]
    resultados.append({
        "host": host_id,
        "rol": role,
        "protocolo": protocolo,
        "duracion_s": round(duracion, 3),
        "bytes": bytes_totales,
        "throughput_kib_s": round(throughput, 3)
    })

# === GUARDAR CSV ===
with open(out_csv, "w", newline="") as csvf:
    fieldnames = [
        "host", "rol", "protocolo", "duracion_s", "bytes", "throughput_kib_s"
    ]
    writer = csv.DictWriter(csvf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(resultados)

print(f"\n Métricas guardadas en: {out_csv}")

# === GRAFICAR RESULTADOS ===
df = pd.DataFrame(resultados)

# Duración media por protocolo
plt.figure()
df.groupby("protocolo")["duracion_s"].mean().plot(
    kind="bar", yerr=df.groupby("protocolo")["duracion_s"].std()
)
plt.ylabel("Segundos")
plt.title("Duración media por protocolo")
plt.tight_layout()
plt.savefig(os.path.join(metricas_dir, "duracion_comparacion.png"))

# Throughput medio por protocolo
plt.figure()
df.groupby("protocolo")["throughput_kib_s"].mean().plot(
    kind="bar", yerr=df.groupby("protocolo")["throughput_kib_s"].std()
)
plt.ylabel("KiB/s")
plt.title("Throughput medio por protocolo")
plt.tight_layout()
plt.savefig(os.path.join(metricas_dir, "throughput_comparacion.png"))
