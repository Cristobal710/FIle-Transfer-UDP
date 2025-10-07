import pandas as pd
import matplotlib.pyplot as plt
import os

metricas_dir = os.path.join(os.getcwd(), "metricas")
csv_path = os.path.join(metricas_dir, "metricas_pcap.csv")

df = pd.read_csv(csv_path)

df_upload = df[df["rol"] == "upload"]
df_download = df[df["rol"] == "download"]

plt.figure()
df_upload.groupby("protocolo")["throughput_kib_s"].mean().plot(
    kind="bar", 
    yerr=df_upload.groupby("protocolo")["throughput_kib_s"].std(),
    color=["#5DADE2", "#58D68D"]
)
plt.title("Comparación Throughput de Upload (SW vs GBN)")
plt.ylabel("Throughput (KiB/s)")
plt.xlabel("Protocolo")
plt.tight_layout()
plt.savefig(os.path.join(metricas_dir, "comparacion_throughput_upload_20%.png"))
plt.close()

# === GRAFICO 2: Download (Stop & Wait vs Go-Back-N) ===
plt.figure()
df_download.groupby("protocolo")["throughput_kib_s"].mean().plot(
    kind="bar", 
    yerr=df_download.groupby("protocolo")["throughput_kib_s"].std(),
    color=["#F5B041", "#BB8FCE"]
)
plt.title("Comparación Throughput de Download (SW vs GBN)")
plt.ylabel("Throughput (KiB/s)")
plt.xlabel("Protocolo")
plt.tight_layout()
plt.savefig(os.path.join(metricas_dir, "comparacion_throughput_download_20%.png"))
plt.close()

print("Gráficos generados:")
print(f"- {os.path.join(metricas_dir, 'comparacion_throughput_upload_20%.png')}")
print(f"- {os.path.join(metricas_dir, 'comparacion_throughput_download_20%.png')}")
