# Aufgabe 4 - Math Factory as a Service

Diese Aufgabe erweitert die Math Factory aus Aufgabe 2 zu einem kleinen serviceorientierten System:

- mehrere skalierbare Math-Factory-Worker als JSON-RPC-Server
- ein JSON-RPC-Gateway, das Requests per Round-Robin auf Worker verteilt
- ein Data Manager für Kosten, Thresholds und WebSocket-Benachrichtigungen
- getrennte Ops- und Customer-Datenbanken
- transaktionales Schreiben beider Datenbanken pro Rechenoperation
- Docker Compose für lokale Tests und eine Swarm-Stack-Datei für Orchestrierung

## Architektur

```text
Client
  |
  | JSON-RPC :8081/rpc
  v
Math Factory Gateway
  |
  | Round-Robin
  v
MF Worker 1..n  --->  Data Manager :8080  --->  Ops DB
                         |                    \
                         | REST/WebSocket       -> Cust DB
                         v
                     Anwendungen
```

Die Worker berechnen nur mathematische Operationen. Nach erfolgreicher Ausführung melden sie dem Data Manager ein `operation_charged`-Event. Der Data Manager schreibt dieses Event in einer atomaren Transaktion in die Ops- und Cust-Datenbank und verschickt bei überschrittenem Threshold WebSocket-Benachrichtigungen.

Für die lokale Implementierung werden zwei SQLite-Dateien genutzt:

- `ops.sqlite3`
- `cust.sqlite3`

SQLite wird mit `ATTACH DATABASE` so verwendet, dass beide Dateien innerhalb einer gemeinsamen Transaktion aktualisiert werden. Für eine echte Multi-Node-Produktionsvariante wäre CockroachDB passend, weil es verteilte SQL-Transaktionen über mehrere Knoten unterstützt.

## Lokal starten

```bash
cd aufgabe4
docker compose up --build
```

Danach sind erreichbar:

- Data Manager REST/OpenAPI: `http://127.0.0.1:8080/docs`
- JSON-RPC Gateway: `http://127.0.0.1:8081/rpc`

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

`session_id` ist in Aufgabe 4 die Anwendungs-ID. Alle Kosten werden unter dieser ID im Data Manager gesammelt.

## Data Manager REST

Threshold setzen:

```bash
curl -X PUT http://127.0.0.1:8080/apps/demo-app/threshold \
  -H 'Content-Type: application/json' \
  -d '{"threshold":100}'
```

Kosten abfragen:

```bash
curl http://127.0.0.1:8080/apps/demo-app/costs
```

Letzte Operationen aus der Ops DB:

```bash
curl http://127.0.0.1:8080/operations
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
{"type":"registered","app_id":"demo-app","total_cost":0,"threshold":100,"threshold_exceeded":false}
{"type":"threshold_updated","app_id":"demo-app","total_cost":0,"threshold":500,"threshold_exceeded":false}
{"type":"threshold_exceeded","app_id":"demo-app","total_cost":127,"threshold":100,"threshold_exceeded":true}
```

## Docker Swarm

Images bauen:

```bash
cd aufgabe4
docker build -f Dockerfile.data-manager -t math-factory-data-manager:latest .
docker build -f Dockerfile.worker -t math-factory-worker:latest .
docker build -f Dockerfile.gateway -t math-factory-gateway:latest .
```

Swarm initialisieren und Stack starten:

```bash
docker swarm init
docker stack deploy -c docker-stack.yml math-factory
docker service ls
```

Worker skalieren:

```bash
docker service scale math-factory_math-factory-worker=5
```

## Transaktionen

Die modellierten Transaktionen stehen in [TRANSACTIONS.md](TRANSACTIONS.md). Dort sind Austauschvorgänge, Beispiel-History und Serialisierungsgraph beschrieben. Der Graph ist azyklisch.

## Tests

```bash
cd aufgabe4
PYTHONPATH=src ../aufgabe2/.venv/bin/python -m unittest discover -s tests
```
