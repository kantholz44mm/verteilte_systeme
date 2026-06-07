# Aufgabe 4 - Math Factory as a Service

Diese Aufgabe erweitert die Math Factory aus Aufgabe 2 zu einem kleinen serviceorientierten System:

- mehrere skalierbare Math-Factory-Worker als JSON-RPC-Server
- ein JSON-RPC-Gateway, das Requests per Round-Robin auf Worker verteilt und
  REST-Admin-Anfragen an alle Worker weiterleitet
- ein Data Manager für Kosten, Thresholds und WebSocket-Benachrichtigungen
- getrennte Ops- und Customer-Datenbanken
- transaktionales Schreiben beider Datenbanken pro Rechenoperation
- Docker Compose für lokale Tests und eine Swarm-Stack-Datei für Orchestrierung

## Architektur

```text
Client
  |
  | JSON-RPC  :8081/rpc
  | REST-Admin :8081/operations
  v
Math Factory Gateway
  |
  | Round-Robin (JSON-RPC)
  | Broadcast  (REST-Admin an alle Worker)
  v
MF Worker 1..n
  |
  | HTTP POST /events/operation
  v
Data Manager :8080
  |
  | atomare Transaktion (SQLite ATTACH)
  +---> ops.sqlite3   (Ops DB)
  +---> cust.sqlite3  (Cust DB)
  |
  | WebSocket /ws
  v
Anwendungen
```

Die Worker berechnen ausschließlich mathematische Operationen und greifen
**nicht** direkt auf Datenbanken zu. Nach erfolgreicher Ausführung senden sie
dem Data Manager ein `operation_charged`-Event. Der Data Manager schreibt
dieses Event in einer atomaren Transaktion in beide Datenbanken und verschickt
bei überschrittenem Threshold WebSocket-Benachrichtigungen.

Für die lokale Implementierung werden zwei SQLite-Dateien genutzt:

- `ops.sqlite3` – Ops DB (serverinstanzbezogene Daten)
- `cust.sqlite3` – Cust DB (anwendungsbezogene Daten)

SQLite wird mit `ATTACH DATABASE` so verwendet, dass beide Dateien innerhalb
einer gemeinsamen Transaktion aktualisiert werden. Für eine echte
Multi-Node-Produktionsvariante wäre CockroachDB passend, weil es verteilte
SQL-Transaktionen über mehrere Knoten unterstützt.

## Lokal starten

```bash
cd aufgabe4
docker compose up --build
```

Danach sind erreichbar:

- Data Manager REST/OpenAPI: `http://127.0.0.1:8080/docs`
- JSON-RPC Gateway:          `http://127.0.0.1:8081/rpc`
- REST-Admin via Gateway:    `http://127.0.0.1:8081/operations`

## JSON-RPC Beispiel

```bash
curl -X POST http://127.0.0.1:8081/rpc \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "addition",
    "params": {
      "a": 3,
      "b": 4,
      "session_id": "demo-app"
    }
  }'
```

`session_id` im JSON-RPC-Request ist die Anwendungs-ID. Alle Kosten werden
unter dieser ID im Data Manager als `app_id` geführt.

## REST-Admin (Operationen verwalten)

Die Admin-Anfragen werden vom Gateway an **alle** Worker weitergeleitet
(Broadcast), sodass der Zustand auf allen Instanzen konsistent bleibt.

Alle Operationen auflisten:

```bash
curl http://127.0.0.1:8081/operations
```

Eine Operation abfragen:

```bash
curl http://127.0.0.1:8081/operations/power
```

Kosten einer Operation ändern:

```bash
curl -X PATCH http://127.0.0.1:8081/operations/power \
  -H 'Content-Type: application/json' \
  -d '{"cost": 800}'
```

Operation deaktivieren / aktivieren:

```bash
curl -X PATCH http://127.0.0.1:8081/operations/power \
  -H 'Content-Type: application/json' \
  -d '{"enabled": false}'
```

## Data Manager REST

### Ops DB – Serverinstanz-bezogene Daten

Alle Operationen (was, Kosten, für welche App, welche Instanz):

```bash
curl http://127.0.0.1:8080/operations
curl http://127.0.0.1:8080/operations?limit=20
```

Operationen einer bestimmten Anwendung aus der Ops DB:

```bash
curl "http://127.0.0.1:8080/operations?app_id=demo-app"
```

Server-Instanz-Statistiken (Requests, Gesamtkosten, distinct Apps pro Instanz):

```bash
curl http://127.0.0.1:8080/instances/stats
```

### Cust DB – Anwendungsbezogene Daten

Alle bekannten Anwendungen mit Gesamtkosten und Threshold-Status:

```bash
curl http://127.0.0.1:8080/apps
```

Welche Operationen hat eine Anwendung angefordert, zu welchem Preis,
auf welcher Instanz (aus `cust.charge_log`):

```bash
curl http://127.0.0.1:8080/apps/demo-app/operations
```

Gesamtkosten und Threshold-Status einer Anwendung:

```bash
curl http://127.0.0.1:8080/apps/demo-app/costs
```

Threshold setzen:

```bash
curl -X PUT http://127.0.0.1:8080/apps/demo-app/threshold \
  -H 'Content-Type: application/json' \
  -d '{"threshold":100}'
```

## WebSocket

Der Data Manager bietet `ws://127.0.0.1:8080/ws`.

Client-Nachrichten:

```json
{"action":"register","app_id":"demo-app","threshold":100}
{"action":"set_threshold","app_id":"demo-app","threshold":500}
{"action":"ping"}
```

Server-Nachrichten:

```json
{"type":"threshold_updated","app_id":"demo-app","total_cost":0,"threshold":100,"threshold_exceeded":false}
{"type":"registered","app_id":"demo-app","total_cost":0,"threshold":100,"threshold_exceeded":false}
{"type":"threshold_exceeded","app_id":"demo-app","total_cost":127,"threshold":100,"threshold_exceeded":true,"message":"Der konfigurierte Kostenschwellwert wurde überschritten."}
{"type":"pong"}
```

Hinweis zur Reihenfolge: Enthält die `register`-Nachricht ein `threshold`-Feld,
sendet der Server zuerst `threshold_updated`, danach `registered`. Wird der
Threshold dabei sofort überschritten, folgt zusätzlich `threshold_exceeded`.

## Docker Swarm

Images bauen:

```bash
cd aufgabe4
docker build -f Dockerfile.data-manager -t math-factory-data-manager:latest .
docker build -f Dockerfile.worker       -t math-factory-worker:latest       .
docker build -f Dockerfile.gateway      -t math-factory-gateway:latest      .
```

Swarm initialisieren und Stack starten:

```bash
# Bei mehreren Netzwerkadressen muss --advertise-addr gesetzt werden:
docker swarm init --advertise-addr <IP>
docker stack deploy -c docker-stack.yml math-factory
docker service ls
```

Worker skalieren:

```bash
docker service scale math-factory_math-factory-worker=5
```

Im Swarm-Modus wird der Worker-Service mit `endpoint_mode: dnsrr` betrieben,
damit das Gateway per DNS-Round-Robin auf einzelne Replikate zugreifen kann
statt auf eine gemeinsame VIP.

Aufräumen:

```bash
docker stack rm math-factory
docker swarm leave --force
```

## Transaktionen

Die modellierten Transaktionen stehen in [TRANSACTIONS.md](TRANSACTIONS.md).
Dort sind die genauen Datenbankzugriffe, eine Beispiel-History und der
Serialisierungsgraph beschrieben. Der Graph ist azyklisch – die History ist
konfliktserialisierbar.

## Tests

```bash
cd aufgabe4
PYTHONPATH=src ../aufgabe2/.venv/bin/python -m unittest discover -s tests -v
```
