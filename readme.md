

# Aufgabenblatt 1

## Setup

### Benötigte Tools
- Docker
- Docker Compose
- Netcat

### Starten der Anwendung

Das Deployment erfolgt über: ```docker compose up```

**Wichtiger Hinweis**

Docker muss so konfiguriert sein, dass Host Networking aktiviert ist.

Dies kann in Docker Desktop unter folgendem Pfad eingestellt werden:

```Settings → Resources → Network → Enable host networking```

## Skript

Rust Skript TODO
 

## Architektur

Die Anwendung besteht aus drei Containern, die miteinander kommunizieren und Daten schrittweise verarbeiten. Die Konfiguration erfolgt zentral über die `docker-compose.yml`, in der sowohl die Container als auch deren Umgebungsvariablen definiert sind.

Jeder Container wird über Umgebungsvariablen gesteuert. Diese sind:

- ``` SEND_ADDRESS```  gibt die Zieladresse (IP:Port) an, an die ein Container sein Ergebnis weiterleitet.

- ```LISTEN_PORT``` definiert den UDP-Port, auf dem der Container eingehende Nachrichten empfängt.

- ```OPERATION``` legt fest, welche Verarbeitung durchgeführt wird (z. B. inc, dec, shl, shr).

- ```SOCKETTYPE ```bestimmt das verwendete Protokoll, entweder udp oder tcp.

```
Host ->  C1  ->  C2  ->  C3  -> Host
```

| Container | ID (Name) |  Listen Port | Send Address |  Operation |
|----------|----------|-------------|--------------|-----------|
| c1 | verteilte_systeme-c1-1 | 8080 | 127.0.0.1:8081 |  inc |
| c2 | verteilte_systeme-c2-1 | 8081 | 127.0.0.1:8082 |  shl |
| c3 | verteilte_systeme-c3-1 | 8082 | 127.0.0.1:8090 |  dec |


| Operation | Beschreibung |
|----------|-------------|
| inc | Erhöht den empfangenen Wert um 1 |
| shl | Bit-Shift nach links (Multiplikation mit 2) |
| shr | Bit-Shift nach rechts (Division durch 2, ganzzahlig) |
| dec | Verringert den Wert um 1 |

## Kommunikation (UDP / TCP)

Die Kommunikation zwischen den Containern erfolgt wahlweise über UDP oder TCP.  
Dies wird über die Umgebungsvariable `SOCKETTYPE` in der `docker-compose.yml` gesteuert.

Der Ablauf der Datenverarbeitung ist in beiden Fällen identisch:
Eine Zahl wird vom Host an den ersten Container (`c1`) gesendet, anschließend von den Containern nacheinander verarbeitet (`inc → shl → dec`) und am Ende wieder an den Host zurückgegeben.

### Befehle fürs Senden & Empfangen

| Protokoll | Senden | Empfangen |
|----------|--------|----------|
| UDP | `echo "[Zahl]" \| netcat -u 127.0.0.1 8080` | `nc -ul 8090` |
| TCP | `echo "[Zahl]" \| netcat 127.0.0.1 8080` | `nc -l 8090` |




### UDP vs TCP

**UDP** ist ein verbindungsloses Protokoll. Gesendete Pakete werden ohne Bestätigung übertragen, wodurch Verluste ignoriert werden. Dies ermöglicht eine schnelle Kommunikation mit geringer Latenz, jedoch ohne Garantie, dass Daten beim Empfänger ankommen.
````
UDP:
Instanz A                    Instanz B
    │                            │
    │  UDP Paket senden          │
    ├──────────────────────────► │
    │                            │
````
UDP eignet sich für Anwendungen mit geringer Latenz, bei denen Datenverluste tolerierbar sind, z.B. Streaming oder Echtzeitkommunikation

---

**TCP** ist verbindungsorientiert. Vor der Datenübertragung wird eine Verbindung aufgebaut, und der Empfang von Daten wird bestätigt. Dadurch wird sichergestellt, dass Daten vollständig und in der richtigen Reihenfolge ankommen.


````
TCP:
Instanz A                    Instanz B
    │                            │
    │  SYN                       │
    ├──────────────────────────► │
    │  SYN-ACK                   │
    │ ◄──────────────────────────┤
    │  ACK                       │
    ├──────────────────────────► │
─ ─ |─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │─ ─  Connection establishment
    │                            │
    │  Datenübertragung          │
    ├──────────────────────────► │
    │                            │
    │  (Bestätigung).            │
    │ ◄──────────────────────────┤
````
Eignet sich für Anwendungen, bei denen Zuverlässigkeit entscheidend ist, z.B. Datenbanken, Webanwendungen oder Dateiübertragungen.

## TODO Beschreiben Sie kurz

• die Unterschiede zwischen der Verwendung von TCP und UDP in Ihrem Pro-
gramm in Bezug auf die **Containerkommunikation und Start-up Verhalten.**


• wie sich ein Serialisierungsformat (z.B. JSON, Protobuf) auf die 
Kommunikation zwischen Containern in dieser Aufgabe auswirken würde.
