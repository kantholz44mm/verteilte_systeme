# Aufgabe 2 - Math Factory mit REST, JSON-RPC und WebSocket

Diese Implementierung löst die praktischen Teile von Aufgabe 2 komplett in `aufgabe2` und verwendet jetzt bewusst echte Libraries:

- `FastAPI` fuer REST und WebSocket
- `uvicorn` als ASGI-Server
- `httpx` fuer den JSON-RPC-Client
- `websockets` fuer die WebSocket-Clientseite

## Q1: Vergleich JSON-RPC und gRPC

JSON-RPC ist ein leichtgewichtiges RPC-Protokoll, das JSON zur Serialisierung nutzt und häufig über HTTP transportiert wird. Dadurch ist es sehr einfach zu verstehen, leicht mit Browsern, Skripten und heterogenen Systemen integrierbar und für schnelle Prototypen oder kleine Service-Schnittstellen gut geeignet.

gRPC ist stärker formalisiert: Es nutzt Protocol Buffers, arbeitet effizient binaer, unterstützt Streaming nativ und ist bei grossen Datenmengen oder performancekritischen Microservices meist schneller. Rückwärtskompatibilität ist bei gRPC durch Protobuf-Schemaentwicklung strukturierter, während JSON-RPC flexibler, aber auch fehleranfälliger ist. JSON-RPC eignet sich besonders für einfache Remote-Aufrufe, Debugging-freundliche APIs und Umgebungen, in denen menschenlesbare Nachrichten wichtiger sind als maximale Performance.

## Umsetzung

Der Server bietet drei getrennte Schnittstellen:

- REST auf Port `8080` zur Verwaltung der verfuegbaren Operationen und ihrer Kosten
- JSON-RPC auf Port `8081` fuer die eigentlichen Rechenaufrufe
- WebSocket auf Port `8082` fuer Threshold- und Kostenbenachrichtigungen

Unterstuetzte Operationen gemaess Aufgabenblatt:

| Operation | Ausdruck | Kosten |
| --- | --- | ---: |
| `addition` | `a + b` | 2 |
| `subtraction` | `a - b` | 3 |
| `multiplication` | `a * b` | 25 |
| `division` | `a / b` | 50 |
| `factorial` | `a!` | 100 |
| `power` | `a^b` | 1150 |

Der Client berechnet `e^x` über die Taylor-Reihe

```text
e^x = sum_{n=0..N} x^n / n!
```

und delegiert dabei alle Rechenschritte per JSON-RPC an den Server. Fuer die Abrechnung wird eine UUID erzeugt und bei jedem Remote-Aufruf mitgeschickt. Ueber die WebSocket-Schnittstelle registriert der Client ausserdem einen Schwellwert; sobald die kumulierten Kosten ihn überschreiten, beendet der Client die Berechnung und gibt den letzten Zwischenstand aus.

REST und OpenAPI werden automatisch von FastAPI generiert. Dadurch sind `docs` und `openapi.json` direkt aus der implementierten API ableitbar und nicht mehr als statische Datei gepflegt.

## Projektstruktur

```text
aufgabe2/
  src/math_factory/
    client.py
    operations.py
    rpc.py
    schemas.py
    server.py
    state.py
  tests/
  Dockerfile.server
  Dockerfile.client
  docker-compose.yml
  requirements.txt
```

## Lokal starten

Server:

```bash
cd aufgabe2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python3 -m math_factory.server
```

Client:

```bash
cd aufgabe2
source .venv/bin/activate
PYTHONPATH=src python3 -m math_factory.client --server-host localhost --x 1.0 --terms 8 --threshold 2500
```

## REST API

Die REST-API dient zur Verwaltung der freigegebenen Rechenoperationen. OpenAPI-Dokumentation liegt unter:

- `http://localhost:8080/openapi.json`
- `http://localhost:8080/docs`

Beispiele:

```bash
curl http://localhost:8080/operations
curl http://localhost:8080/operations/power
curl -X PATCH http://localhost:8080/operations/power \
  -H 'Content-Type: application/json' \
  -d '{"cost": 900, "enabled": true}'
```

## JSON-RPC Beispiel

```bash
curl -X POST http://localhost:8081/rpc \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "addition",
    "params": {
      "a": 5,
      "b": 7,
      "session_id": "demo-session"
    }
  }'
```

## WebSocket-Protokoll

Client-Nachrichten:

```json
{"action":"register","session_id":"...","threshold":2500}
{"action":"set_threshold","session_id":"...","threshold":5000}
```

Server-Nachrichten:

```json
{"type":"registered","session_id":"...","threshold":2500,"total_cost":0,"threshold_exceeded":false}
{"type":"threshold_updated","session_id":"...","threshold":2500,"total_cost":1302,"threshold_exceeded":false}
{"type":"threshold_exceeded","session_id":"...","threshold":2500,"total_cost":2604,"message":"The configured cost threshold has been exceeded."}
```

## Docker

Alles zusammen starten:

```bash
cd aufgabe2
docker compose up --build
```

Dabei wird der Server auf den Ports `8080`, `8081` und `8082` exponiert. Der Client verbindet sich automatisch zum Dienst `math-factory-server`.

## Tests

```bash
cd aufgabe2
source .venv/bin/activate
PYTHONPATH=src python3 -m unittest discover -s tests
```
