import pandas as pd
import matplotlib.pyplot as plt
import os

# === Configuración de rutas ===
metricas_dir = os.path.join(os.getcwd(), "metricas")
csv_path = os.path.join(metricas_dir, "metricas_pcap.csv")

# Cargar datos
df = pd.read_csv(csv_path)

# Filtrar por rol
df_upload = df[df["rol"] == "upload"]
df_download = df[df["rol"] == "download"]

# === GRAFICO 1: Duración Upload (Stop & Wait vs Go-Back-N) ===
plt.figure()
df_upload.groupby("protocolo")["duracion_s"].mean().plot(
    kind="bar",
    yerr=df_upload.groupby("protocolo")["duracion_s"].std(),
    color=["#5DADE2", "#58D68D"]
)
plt.title("Duración de Upload (SW vs GBN)")
plt.ylabel("Duración promedio (s)")
plt.xlabel("Protocolo")
plt.tight_layout()
plt.savefig(os.path.join(metricas_dir, "duracion_upload_20%.png"))
plt.close()

# === GRAFICO 2: Duración Download (Stop & Wait vs Go-Back-N) ===
plt.figure()
df_download.groupby("protocolo")["duracion_s"].mean().plot(
    kind="bar",
    yerr=df_download.groupby("protocolo")["duracion_s"].std(),
    color=["#F5B041", "#BB8FCE"]
)
plt.title("Duración de Download (SW vs GBN)")
plt.ylabel("Duración promedio (s)")
plt.xlabel("Protocolo")
plt.tight_layout()
plt.savefig(os.path.join(metricas_dir, "duracion_download_20%.png"))
plt.close()

print(" Gráficos generados:")
print(f"- {os.path.join(metricas_dir, 'duracion_upload_20%.png')}")
print(f"- {os.path.join(metricas_dir, 'duracion_download_20%.png')}")
