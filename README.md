# FIle-Transfer-UDP

Trabajo Practico realizado para la Universidad de Buenos Aires, facultad de Ingenieria (FIUBA) donde la finalidad es, utilizando el protocolo de transporte UDP, conseguir una funcionalidad simil al protocolo TCP utilizando diferentes mecanismos para la transferencia de archivos a traves de sockets con una arquitectura Cliente-Servidor.



Para correr el programa:

primero correr en una terminal python3 server.py para levantar el servidor y ponerse a escuchar paquetes.

luego en cualquier otra terminal correr python3 client.py 

# Mininet

- Pararse en el root del proyecto
- Correr `sudo python3 src/mininet_udp_topo.py`
- Se levantan dos terminales, una en un nodo h1 con IP 10.0.0.1 y la otra con un cliente en el nodo h2 con IP 10.0.0.2
- Upload -> OK
- Download -> WIP

```mininet > h1 tc qdisc add dev h1-eth0 root netem loss 20%``` -> fuerza que se pierdan el 20% de los paquetes que envía h1

# Upload with help
python3 src/interface.py upload -h

# Upload a file
python3 src/interface.py upload -s /path/to/file.pdf -n myfile.pdf -v

# Upload with custom server
python3 src/interface.py upload -H 192.168.1.100 -p 8080 -s test.txt -n uploaded.txt

# Download a file  
python3 src/interface.py download -n myfile.pdf -d /downloads/received.pdf -v