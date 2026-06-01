# Aufgabe 5 - Distributed Chat Service

Diese Loesung implementiert eine homogene Peer-Software in Python. Jeder Prozess ist gleichzeitig API-Server, Chat-UI, Gossip-Knoten und Speicher für die lokal bekannten Nachrichten.

Python hat keine so ausgereifte libp2p-Implementierung mit GossipSub, Kademlia, Noise und Yamux wie Rust oder Go. Deshalb bildet diese Abgabe die geforderten Konzepte in Python auf HTTP/WebSocket ab: Topics entsprechen Chaträumen, Peer-Discovery passiert ueber Bootstrap-Peers, Gossip propagiert Nachrichten, und ein Anti-Entropy-Sync sorgt für Eventual Consistency.

## Abgebildete Anforderungen

- **Virtualisation:** `docker-compose.yml` startet fünf identische Peer-Container. Weitere Peers können mit `docker compose up --scale` oder eigenen Services ergänzt werden.
- **Kommunikation:** Jeder Chatraum ist ein Topic. Nachrichten werden per Gossip an bekannte Peers weitergeleitet.
- **Auslieferungsgarantien:** Das System nutzt immer `qos=2`: Zustellungen werden wiederholt versucht und pro Peer über eine `delivery_id` idempotent genau einmal angenommen.
- **Synchronisation:** Jede Nachricht bekommt eine physische Zeit und einen Hybrid Logical Clock Timestamp. Der Verlauf wird nach HLC sortiert.
- **Eventual Consistency:** Fehlgeschlagene Zustellungen landen in einer Outbox und werden erneut versucht. Zusätzlich gleicht ein Anti-Entropy-Loop periodisch alle bekannten Nachrichten zwischen Peers ab.
- **GUI:** Jeder Peer liefert unter `/` eine WhatsApp-ähnliche Gruppenchat-Oberfläche aus. Gruppen sind dabei die Chaträume/Topics.
- **Identität:** Der Anzeigename einer Nachricht ist immer die Container-/Peer-ID aus `PEER_ID`, zum Beispiel `peer1`.

## Projektstruktur

```text
aufgabe5/
  src/distributed_chat/
    hlc.py
    models.py
    peer.py
    store.py
  tests/
  Dockerfile
  docker-compose.yml
  requirements.txt
```

## Lokal starten

```bash
cd aufgabe5
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src PEER_ID=peer1 PORT=8001 BASE_URL=http://127.0.0.1:8001 python3 -m distributed_chat.peer
```

In einem zweiten Terminal:

```bash
cd aufgabe5
source .venv/bin/activate
PYTHONPATH=src PEER_ID=peer2 PORT=8002 BASE_URL=http://127.0.0.1:8002 BOOTSTRAP_PEERS=http://127.0.0.1:8001 python3 -m distributed_chat.peer
```

Danach:

- Peer 1 UI: `http://127.0.0.1:8001`
- Peer 2 UI: `http://127.0.0.1:8002`
- Swagger/OpenAPI je Peer: `/docs`

## Docker

```bash
cd aufgabe5
docker compose up --build
```

Die fünf Peers sind dann erreichbar unter:

- `http://127.0.0.1:8001`
- `http://127.0.0.1:8002`
- `http://127.0.0.1:8003`
- `http://127.0.0.1:8004`
- `http://127.0.0.1:8005`

## REST-Beispiele

Nachricht an einem Peer veröffentlichen:

```bash
curl -X POST http://127.0.0.1:8001/messages \
  -H 'Content-Type: application/json' \
  -d '{"room":"general","text":"Hallo verteiltes System"}'
```

Verlauf auf einem anderen Peer lesen:

```bash
curl http://127.0.0.1:8002/rooms/general/messages
```

Peer manuell bekannt machen:

```bash
curl -X POST http://127.0.0.1:8001/peers \
  -H 'Content-Type: application/json' \
  -d '{"peer_id":"peer2","base_url":"http://127.0.0.1:8002"}'
```

## Tests

```bash
cd aufgabe5
PYTHONPATH=src python3 -m unittest discover -s tests
```

r.
