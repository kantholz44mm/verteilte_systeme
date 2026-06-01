# Transaktionsmodell

## Datenobjekte

- `O_i`: Ops-DB-Eintrag für Operation `i`
- `C_a`: Customer-DB-Zustand der Anwendung `a`, vor allem `total_cost`, `threshold`, `threshold_exceeded`
- `N_a`: Notification-Ereignis für Anwendung `a`

## Transaktionen

`T1`: Worker `mf-1` führt `addition` für Anwendung `demo-app` aus.

```text
r1(C_demo)
w1(O_1)
w1(C_demo.total_cost = C_demo.total_cost + 2)
c1
```

`T2`: Data Manager setzt den Threshold für `demo-app`.

```text
r2(C_demo)
w2(C_demo.threshold = 100)
c2
```

`T3`: Worker `mf-2` führt `power` für `demo-app` aus und überschreitet den Threshold.

```text
r3(C_demo)
w3(O_2)
w3(C_demo.total_cost = C_demo.total_cost + 1150)
w3(C_demo.threshold_exceeded = true)
w3(N_demo)
c3
```

`T4`: Anwendung fragt Kosten ab.

```text
r4(C_demo)
c4
```

## Beispiel-History

Eine serialisierbare Ausführung:

```text
H =
r1(C_demo)
w1(O_1)
w1(C_demo.total_cost)
c1
r2(C_demo)
w2(C_demo.threshold)
c2
r3(C_demo)
w3(O_2)
w3(C_demo.total_cost)
w3(C_demo.threshold_exceeded)
w3(N_demo)
c3
r4(C_demo)
c4
```

## Konflikte

- `T1 -> T2`, weil `T1` `C_demo.total_cost` schreibt und `T2` danach `C_demo` liest.
- `T2 -> T3`, weil `T2` `C_demo.threshold` schreibt und `T3` danach `C_demo` liest.
- `T3 -> T4`, weil `T3` `C_demo.total_cost` und `C_demo.threshold_exceeded` schreibt und `T4` danach `C_demo` liest.

## Serialisierungsgraph

```text
T1 ---> T2 ---> T3 ---> T4
```

Der Graph enthält keine Zyklen. Die History ist daher konfliktserialisierbar und äquivalent zur seriellen Reihenfolge:

```text
T1, T2, T3, T4
```

## Konsistenz über Ops DB und Cust DB

Pro Rechenoperation schreibt der Data Manager:

1. einen fachlichen Operationseintrag in die Ops DB,
2. einen Charge-Eintrag in die Cust DB,
3. den aggregierten Kostenstand der Anwendung in die Cust DB,
4. optional den Threshold-Status.

Diese Schritte laufen in einer gemeinsamen Transaktion. In der lokalen Implementierung wird SQLite mit `ATTACH DATABASE` genutzt. Für echte Multi-Node-Transaktionen ist CockroachDB die naheliegende Wahl, weil es verteilte SQL-Transaktionen mit serialisierbarer Isolation unterstützt.
