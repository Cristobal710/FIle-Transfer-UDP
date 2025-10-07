import pandas as pd
import matplotlib.pyplot as plt
import os

metricas_dir = os.path.join(os.getcwd(), "metricas")

# Asociar cada archivo CSV a su tamaño
archivos = {
    "1 MB": "metricas_pcap_1mb.csv",
    "5 MB": "metricas_pcap_5mb.csv",
    "10 MB": "metricas_pcap_10mb.csv"
}

data = []

# Leer cada CSV y agregar el tamaño correspondiente
for tam, fname in archivos.items():
    path = os.path.join(metricas_dir, fname)
    df = pd.read_csv(path)
    df["tamano"] = tam
    data.append(df)

df_all = pd.concat(data)

# Agrupar por tamaño y protocolo
resultados = df_all.groupby(["tamano", "protocolo"])["duracion_s"].mean().reset_index()

# Graficar
plt.figure()
for protocolo in resultados["protocolo"].unique():
    subset = resultados[resultados["protocolo"] == protocolo]
    plt.plot(subset["tamano"], subset["duracion_s"], marker='o', label=protocolo)

plt.title("Duración de transferencia vs Tamaño de archivo")
plt.xlabel("Tamaño del archivo")
plt.ylabel("Duración promedio (s)")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(metricas_dir, "duracion_vs_tamano.png"))

print(" Gráfico generado: metricas/duracion_vs_tamano.png")
