

# Aufgabenblatt 1

## Setup

### Benötigte Tools
- Docker
- Docker Compose
- Netcat

### Starten der Anwendung

Das Deployment erfolgt über: ```docker compose up```

## Architektur

Die Anwendung besteht aus drei Containern, die miteinander kommunizieren und Daten schrittweise verarbeiten. Die Konfiguration erfolgt zentral über die `docker-compose.yml`, in der sowohl die Container als auch deren Umgebungsvariablen definiert sind.

Jeder Container wird über Umgebungsvariablen gesteuert. Diese sind:

- ``` SEND_ADDRESS```  gibt die Zieladresse (IP/Name:Port) an, an die ein Container sein Ergebnis weiterleitet.

- ```LISTEN_ADDRESS``` definiert die Adresse an, auf dem der Container eingehende Nachrichten empfängt (IP/Name:Port).

- ```OPERATION``` legt fest, welche Verarbeitung durchgeführt wird (z. B. inc, dec, shl, shr).

- ```SOCKETTYPE ``` bestimmt das verwendete Protokoll, entweder udp oder tcp.

```
Host ->  C1  ->  C2  ->  C3  -> Host
```

| Container | ID (Name) |  Listen Address | Send Address |  Operation |
|----------|----------|-------------|--------------|-----------|
| c1 | verteilte_systeme-c1-1 | 0.0.0.0:8080 | c2:8080 |  inc |
| c2 | verteilte_systeme-c2-1 | 0.0.0.0:8080 | c3:8080 |  shl |
| c3 | verteilte_systeme-c3-1 | 0.0.0.0:8080 | host.docker.internal:8080 |  dec |


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

Angenommen, der erste Container hat die IP `172.17.0.4` (docker inspect ...):

| Protokoll | Senden | Empfangen |
|----------|--------|----------|
| UDP | `echo "[Zahl]" \| netcat -u 172.17.0.4 8080` | `nc -ul 8080` |
| TCP | `echo "[Zahl]" \| netcat 172.17.0.4 8080` | `nc -l 8080` |


### UDP vs TCP

#### Unterschiede zwischen TCP/UDP in unserem Programm
k
Grundsätzlich ist beides als synchrone Kommunikation implementiert (blockierende Sockets). Auch bei TCP wird lediglich mit `accept` eine Verbindung akzeptiert, deren Daten eingelesen und die berechneten Daten in einem weiteren Socket an den Ausgangspartner weitergeleitet. Die Lebensdauer beider Sockets ist nur sehr kurz. Das Startupverhalten bei TCP beinhaltet den Handshake, weshalb die initiale Verbindung etwas länger dauert. Bei UDP ist kein Handshake erforderlich, die Nachricht wird "direkt" gesendet und empfangen. TCP hat theoretisch noch den "Slow Start", bei dem die ersten Pakete mit verringerter Datenrate übertragen werden, was in dieser Anwendung nicht zum Tragen kommt, weil nur sehr kleine Datenmengen übertragen werden. Nagle's Algorithmus wird durch Setzen des Flags `TCP_NODELAY` und manuelles Flushing der Streams "eliminiert", dadurch kommt es auch hier nicht zu nennenswerten Verzögerungen.

#### Eignung von TCP/UDP für verschiedene Anwendungen

TCP eignet sich für die integrierte QoS, wodurch eine Auslieferung und der Empfang einer Nachricht bestätigt werden kann. Zudem wird garantiert, dass Nachrichten in der korrekten Reihenfolge ankommen. UDP hat diese Features nicht, ist dafür aber deutlich leichtgewichtiger. UDP kann verwendet werden, wenn der unbedingt korrekte Transfer nicht notwendig ist. Das ist z.B. der Fall bei sehr kurzlebigen Daten, i.e Audio-/Videostreams oder Positionsdaten in Multiplayer-Spielen. Ein einzelnes verlorenes Paket beeinträchtigt das Endergebnis nur minimal und ist daher verkraftbar. TCP sollte verwendet werden, wenn eine Empfangsbestätigung notwendig ist. Bei verteilten Systemen gibt es oft einen Replikationsparameter (Redundanzgrad), der entscheidet, wie viele Kopien eines Datums das System bereithalten soll. Je nach Höhe dieses Parameters kann es generell verkraftbar sein, ein einzelnes Paket zu verlieren.


#### Auswirkung von Serialisierungsformat

Die Zahlen werden zwischen allen Teilnehmern als ASCII-Codierte Zahlenstrings serialisiert. Bei Textbasierten Formaten wie JSON wäre die Serialisierung ähnlich, Protobuf codiert Zahlen in einem Binärformat. Generell muss auf die korrekte Endianness bei der Übetragung geachtet werden, was aber bei ASCII-codierten Zahlenstrings kein Problem ist.
