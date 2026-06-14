# Transaktionsmodell

## Architektur-Hinweis

Die Worker greifen **nicht** direkt auf Datenbanken zu. Jeder Worker:

1. Führt die Rechenoperation im Arbeitsspeicher aus.
2. Sendet ein `operation_charged`-Event per HTTP-POST an den Data Manager.

Der Data Manager übernimmt **alle** Datenbankzugriffe und schreibt Ops DB und
Cust DB atomisch in einer gemeinsamen Transaktion (SQLite `ATTACH DATABASE`).
WebSocket-Benachrichtigungen werden **nach** dem Commit verschickt und sind
daher kein Teil der Datenbanktransaktion.

## Datenobjekte

- `O_i`: Eintrag in `ops.operation_log` für Operation `i`
- `C_a`: Zustand der Anwendung `a` in `cust.applications`
  (Felder: `total_cost`, `threshold`, `threshold_exceeded`)
- `L_i`: Eintrag in `cust.charge_log` für Operation `i`

## Transaktionen

`T1`: Data Manager verarbeitet `addition`-Event von Worker mf-1 für `demo-app`.

```text
w1(O_1)
w1(L_1)
r1(C_demo)
w1(C_demo.total_cost = C_demo.total_cost + 2)
c1
--- nach Commit: keine WS-Benachrichtigung (Threshold nicht überschritten) ---
```

`T2`: Client setzt den Threshold für `demo-app` via REST `PUT /apps/demo-app/threshold`.

```text
r2(C_demo)
w2(C_demo.threshold = 100)
w2(C_demo.threshold_exceeded)
c2
--- nach Commit: WS-Nachricht "threshold_updated" ---
```

`T3`: Data Manager verarbeitet `power`-Event von Worker mf-2 für `demo-app`;
Threshold wird überschritten.

```text
w3(O_2)
w3(L_2)
r3(C_demo)
w3(C_demo.total_cost = C_demo.total_cost + 1150)
w3(C_demo.threshold_exceeded = true)
c3
--- nach Commit: WS-Nachricht "threshold_exceeded" ---
```

`T4`: Client fragt Kosten ab via REST `GET /apps/demo-app/costs`.

```text
r4(C_demo)
c4
```

## Beispiel-History

Eine serialisierbare Ausführung (seriell):

```text
H =
w1(O_1) w1(L_1) r1(C_demo) w1(C_demo.total_cost) c1
r2(C_demo) w2(C_demo.threshold) w2(C_demo.threshold_exceeded) c2
w3(O_2) w3(L_2) r3(C_demo) w3(C_demo.total_cost) w3(C_demo.threshold_exceeded) c3
r4(C_demo) c4
```

## Konflikte

| Von | Nach | Grund |
|-----|------|-------|
| T1  | T2   | T1 schreibt `C_demo.total_cost`, T2 liest danach `C_demo` (rw-Konflikt) |
| T1  | T3   | T1 schreibt `C_demo.total_cost`, T3 liest danach `C_demo` (rw-Konflikt) |
| T2  | T3   | T2 schreibt `C_demo.threshold`, T3 liest danach `C_demo` (rw-Konflikt) |
| T3  | T4   | T3 schreibt `C_demo.*`, T4 liest danach `C_demo` (rw-Konflikt) |

## Serialisierungsgraph

```text
T1 ---> T2 ---> T3 ---> T4
T1 ---> T3
```

Der Graph enthält keine Zyklen. Die History ist konfliktserialisierbar und
äquivalent zur seriellen Reihenfolge:

- T1, T2, T3, T4

## Konsistenz über Ops DB und Cust DB

Pro Rechenoperation schreibt der Data Manager in einer einzigen atomaren
Transaktion:

1. `ops.operation_log` ← fachlicher Operationseintrag (Ops DB)
2. `cust.charge_log` ← Abrechnungseintrag (Cust DB)
3. `cust.applications.total_cost` ← aktualisierter Kostenstand (Cust DB)
4. `cust.applications.threshold_exceeded` ← ggf. Threshold-Flag (Cust DB)

Durch den Einsatz von SQLite `ATTACH DATABASE` mit `BEGIN IMMEDIATE` werden
beide Dateien (`ops.sqlite3` und `cust.sqlite3`) in derselben Transaktion
geschrieben. Ein Partial-Write ist damit ausgeschlossen.

Für echte Multi-Node-Transaktionen ist CockroachDB die passende Wahl, da es
verteilte SQL-Transaktionen mit serialisierbarer Isolation über mehrere Knoten
unterstützt.
