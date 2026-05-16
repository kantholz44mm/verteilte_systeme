#set text(lang: "de")

#import "@preview/unify:0.8.0": num, qty, numrange, qtyrange
#import "@preview/cetz:0.3.4": canvas, draw

= Aufgabe 1

$
  delta &= #qty(75, "ms") \
  c &= max(abs(c_"P1"), abs(c_"P2"), abs(c_"P3")) = #qty(100, "us/s", per: "fraction") \
  Delta t &= frac(delta, 2 c) = #qty(375, "s")
$

Laut Tabelle driften alle Clocks allerdings nur in eine Richtung (dank Vorzeichen). Somit ist die Formel $Delta t = frac(delta, 2 c)$ eigentlich nicht korrekt, da diese miteinberechnet, dass die beiden Clocks "auseinander" driften. Wenn T aber keinen Drift hat, wird der Synchronisierungsinterval durch 

$
  Delta t &= frac(delta, c) = #qty(750, "s")
$

gegeben. Wenn allerdings mit "maximale erlaubte Abweichung zwischen den Uhren" auch die Differenz zwischen $P_1$, $P_2$ und $P_3$ gemeint ist, dann ist die maximale Drift-Rate dementsprechend

$
  c &= max(abs(c_"P1" - c_"P2"), abs(c_"P1" - c_"P3"), abs(c_"P2" - c_"P3")) = #qty(150, "us/s", per: "fraction") \
  Delta t &= frac(delta, 2 c) = #qty(250, "s")
$

Auch hier kann man die Vorzeichen aus der Tabelle so interpretieren, dass stets nur in eine Richtung gedriftet wird. Dann wäre bei der obigen Annahme der Synchronisierungsinterval:

$
  Delta t &= frac(delta, c) = #qty(500, "s")
$

Die Fragestellung ist unserer Meinung nach nicht ganz eindeutig.

= Aufgabe 2

TrueTime ist eine von Google entwickelte API, die in Spanner (Googles global verteilte Datenbank) eingesetzt wird. Anders als herkömmliche Zeitquellen liefert TrueTime kein einzelnes Zeitstempel, sondern ein *Intervall `[earliest, latest]`*, das garantiert die echte aktuelle Zeit enthält.

== Funktionsweise

- Jedes Google-Rechenzentrum hat redundante Zeitquellen: *GPS-Empfänger* und *Atomuhren*
- Ein lokaler _Time Master_ aggregiert diese Quellen und erkennt fehlerhafte Quellen durch Mehrheitsentscheid
- Die API gibt `TT.now()` zurück --- ein Intervall mit garantierter Fehlergrenze (typisch *1--7 ms*)
- Bevor eine Transaktion committet, wartet Spanner, bis das Intervall vollständig in der Vergangenheit liegt (_commit wait_) --- das garantiert externe Konsistenz

== Vorteile gegenüber anderen Methoden

#block(breakable: false)[
  #table(
    columns: (auto, 1fr, 1fr),
    table.header([*Methode*], [*Problem*], [*TrueTime*]),
    [NTP],
      [Fehler im Bereich 1--100 ms, keine Fehlergarantie],
      [Bounded uncertainty, typisch < 7 ms],
    [Logische Uhren (Lamport)],
      [Kein Bezug zur Realzeit],
      [Echte Wanduhrzeit],
    [Vektoruhren],
      [Skalieren schlecht, kein Realzeitbezug],
      [O(1) pro Knoten],
    [PTP / IEEE 1588],
      [Hardware nötig, schwer global skalierbar],
      [Global, in GCP-Infrastruktur integriert],
  )
]

*Kernvorteil:* TrueTime macht die Unsicherheit *explizit und garantiert beschränkt*, anstatt sie zu ignorieren. Dadurch kann Spanner globale Transaktionen mit externer Konsistenz ohne zentralen Lock-Manager durchführen.

= Aufgabe 3

== Kausale Abhängigkeit

Kausal abhängig:

$
  a_1 &arrow a_2 arrow a_3 arrow a_4 arrow a_5 \
  b_1 &arrow b_2 arrow b_3 arrow b_4 arrow b_5 \
  c_1 &arrow c_2 arrow c_3 arrow c_4 \
  a_1 &arrow c_1 \
  b_1 &arrow a_2 \
  b_2 &arrow c_2 \
  c_3 &arrow a_3 \
  c_3 &arrow a_4 \
  c_4 &arrow b_4 \
  a_5 &arrow b_5
$

Kausal unabhängig (nicht vollständig):

$
  a_2 &arrow c_2 \
  a_3 &arrow c_4 \
  b_4 &arrow a_5 \
  &dots
$

== Lamport-Zeitstempel

#figure(
  canvas(length: 1.3cm, {
    import draw: *

    // Process lines
    let y-a = 4
    let y-b = 2
    let y-c = 0

    // Draw horizontal process lines
    line((-0.5, y-a), (9.5, y-a), mark: (end: ">"))
    line((-0.5, y-b), (9.5, y-b), mark: (end: ">"))
    line((-0.5, y-c), (9.5, y-c), mark: (end: ">"))

    // Process labels
    content((9.7, y-a), [Process A], anchor: "west")
    content((9.7, y-b), [Process B], anchor: "west")
    content((9.7, y-c), [Process C], anchor: "west")

    // Event points: (x, y, label, anchor)
    let events = (
      // Process A
      (0.5, y-a, $a_1,1$, "south"),
      (2.5, y-a, $a_2,2$, "south"),
      (5.0, y-a, $a_3,5$, "south"),
      (7.0, y-a, $a_4,6$, "south"),
      (8.3, y-a, $a_5,7$, "south"),
      // Process B
      (0.0, y-b, $b_1,1$, "north"),
      (1.2, y-b, $b_2,2$, "south"),
      (5.3, y-b, $b_3,3$, "north"),
      (7.8, y-b, $b_4,6$, "south"),
      (8.8, y-b, $b_5,8$, "north"),
      // Process C
      (0.7, y-c, $c_1,2$, "north"),
      (2.8, y-c, $c_2,3$, "north"),
      (4.2, y-c, $c_3,4$, "north"),
      (5.8, y-c, $c_4,5$, "north"),
    )

    // Draw dots and labels
    for (x, y, lbl, anch) in events {
      circle((x, y), radius: 0.07, fill: black)
      content((x, y), lbl, anchor: anch, padding: 0.1)
    }

    // Message arrows (from, to)
    let arrows = (
      // a1 -> c1
      ((0.5, y-a), (0.7, y-c)),
      // b1 -> a2 
      ((0.0, y-b), (2.5, y-a)),
      // b2 -> c2
      ((1.2, y-b), (2.8, y-c)),
      // c3 -> a3
      ((4.2, y-c), (5.0, y-a)),
      // b3 -> a4
      ((5.3, y-b), (7.0, y-a)),
      // c4 -> b4
      ((5.8, y-c), (7.8, y-b)),
      // a5 -> b5
      ((8.3, y-a), (8.8, y-b)),
    )

    for (from, to) in arrows {
      line(from, to, mark: (end: ">", size: 0.2))
    }
  }),
  caption: [Logische Uhren in einem verteilten System, mit Lamport-Zeitstempeln],
)

== Scalar Clock Condition

$ 
  forall e_1, e_2 in E : &e_1 arrow e_2 ==> C(e_1) < C(e_2) \
  \
  C(a_1) &< C(c_1) <==> 1 < 2 \
  C(b_1) &< C(a_2) <==> 1 < 2 \
  C(b_2) &< C(c_3) <==> 2 < 3 \
  C(c_3) &< C(a_3) <==> 4 < 5 \
  C(b_3) &< C(a_4) <==> 3 < 6 \
  C(c_4) &< C(b_4) <==> 5 < 6 \
  C(a_5) &< C(b_5) <==> 7 < 8 \
$

$==>$ Scalar Clock Condition ist erfüllt.

== Totale Ordnung

$a_1 -> b_1 -> a_2 -> b_2 -> c_1 -> b_3 -> c_2 -> c_3 -> a_3 -> c_4 -> a_4 -> b_4 -> a_5 -> b_5$

Die totale Ordnung kommt nach Anleitung der Vorlesungsfolien 46 - 47 zustande. Dabei wird angenommen, dass die Ordnung zwischen den Prozessen $A < B < C$ ist .

== Vector Clock

#figure(
  canvas(length: 1.3cm, {
    import draw: *

    // Process lines
    let y-a = 4
    let y-b = 2
    let y-c = 0

    // Draw horizontal process lines
    line((-0.5, y-a), (9.5, y-a), mark: (end: ">"))
    line((-0.5, y-b), (9.5, y-b), mark: (end: ">"))
    line((-0.5, y-c), (9.5, y-c), mark: (end: ">"))

    // Process labels
    content((9.7, y-a), [Process A], anchor: "west")
    content((9.7, y-b), [Process B], anchor: "west")
    content((9.7, y-c), [Process C], anchor: "west")

    // Event points: (x, y, label, anchor)
    let events = (
      // Process A
      (0.5, y-a, $a_1,[1, 0, 0]$, "south"),
      (2.5, y-a, $a_2,[2, 1, 0]$, "south"),
      (5.0, y-a, $a_3,[3, 2, 3]$, "south"),
      (7.0, y-a, $a_4,[4, 3, 3]$, "south"),
      (8.3, y-a, $a_5,[5, 3, 3]$, "south"),
      // Process B
      (0.0, y-b, $b_1,[0, 1, 0]$, "north"),
      (1.2, y-b, $b_2,[0, 2, 0]$, "south"),
      (5.3, y-b, $b_3,[0, 3, 0]$, "north"),
      (7.8, y-b, $b_4,[1, 4, 4]$, "south"),
      (8.8, y-b, $b_5,[5, 5, 4]$, "north"),
      // Process C
      (0.7, y-c, $c_1,[1, 0, 1]$, "north"),
      (2.8, y-c, $c_2,[1, 2, 2]$, "north"),
      (4.2, y-c, $c_3,[1, 2, 3]$, "north"),
      (5.8, y-c, $c_4,[1, 2, 4]$, "north"),
    )

    // Draw dots and labels
    for (x, y, lbl, anch) in events {
      circle((x, y), radius: 0.07, fill: black)
      content((x, y), lbl, anchor: anch, padding: 0.1)
    }

    // Message arrows (from, to)
    let arrows = (
      // a1 -> c1
      ((0.5, y-a), (0.7, y-c)),
      // b1 -> a2 
      ((0.0, y-b), (2.5, y-a)),
      // b2 -> c2
      ((1.2, y-b), (2.8, y-c)),
      // c3 -> a3
      ((4.2, y-c), (5.0, y-a)),
      // b3 -> a4
      ((5.3, y-b), (7.0, y-a)),
      // c4 -> b4
      ((5.8, y-c), (7.8, y-b)),
      // a5 -> b5
      ((8.3, y-a), (8.8, y-b)),
    )

    for (from, to) in arrows {
      line(from, to, mark: (end: ">", size: 0.2))
    }
  }),
  caption: [Logische Uhren in einem verteilten System, mit Vektor-Zeitstempeln],
)

=== Vector Clock Condition

$ 
  forall e_1, e_2 in E : e_1 arrow e_2 ==> V(e_1) < V(e_2) \
  "Mit Vektorvergleichsoperation (<):" \
  forall i : V(e_1)[i] <= V(e_2)[i] and exists j : V(e_1)[j] < V(e_2)[j]
$

$
  C(a_1) &< C(c_1) <==> [1, 0, 0] < [1, 0, 1] \
  C(b_1) &< C(a_2) <==> [0, 1, 0] < [2, 1, 0] \
  C(b_2) &< C(c_3) <==> [0, 2, 0] < [1, 2, 2] \
  C(c_3) &< C(a_3) <==> [1, 2, 3] < [3, 2, 3] \
  C(b_3) &< C(a_4) <==> [0, 3, 0] < [4, 3, 3] \
  C(c_4) &< C(b_4) <==> [1, 2, 3] < [1, 4, 4] \
  C(a_5) &< C(b_5) <==> [5, 3, 3] < [5, 5, 4] \
$

$==>$ Vector Clock Condition ist erfüllt.


#page(flipped: true)[
== Aufgabe 4
#figure(
  canvas(length: 1.8cm, {
    import draw: *

    let y1 = 4
    let y2 = 2
    let y3 = 0

    // Request send
    let req-send = 0.2

    // Request receives — one unique x per message
    let req-p1-from-p2 = 2  // P1 receives from P2
    let req-p1-from-p3 = 3  // P1 receives from P3
    let req-p2-from-p1 = 2  // P2 receives from P1
    let req-p2-from-p3 = 3  // P2 receives from P3
    let req-p3-from-p1 = 2  // P3 receives from P1
    let req-p3-from-p2 = 3  // P3 receives from P2

    // Ack send
    let ack-send1 = 4.0
    let ack-send2 = 4.8

    // Ack receives — one unique x per message
    let ack-p1-from-p2 = 6
    let ack-p1-from-p3 = 7
    let ack-p2-from-p1 = 6
    let ack-p2-from-p3 = 7
    let ack-p3-from-p1 = 6
    let ack-p3-from-p2 = 7

    // CS positions
    let p1-cs-start = 7.0
    let p1-cs-end   = 8.0
    let p2-cs-start = 9.0
    let p2-cs-end   = 10.0
    let p3-cs-start = 11.0
    let p3-cs-end   = 12.0

    // Release receives — one unique x per message
    let p1-rel-send     = p1-cs-end
    let p1-rel-p2-recv  = p1-cs-end + 1
    let p1-rel-p3-recv  = p1-cs-end + 1

    let p2-rel-send     = p2-cs-end
    let p2-rel-p1-recv  = p2-cs-end + 1
    let p2-rel-p3-recv  = p2-cs-end + 1

    let p3-rel-send     = p3-cs-end
    let p3-rel-p1-recv  = p3-cs-end + 1
    let p3-rel-p2-recv  = p3-cs-end + 1

    // CS highlight boxes
    for (y, xs, xe) in (
      (y1, p1-cs-start, p1-cs-end),
      (y2, p2-cs-start, p2-cs-end),
      (y3, p3-cs-start, p3-cs-end),
    ) {
      rect((xs, y - 0.25), (xe, y + 0.25), fill: rgb("#d0ecd0"), stroke: none)
    }

    // Process lines
    line((-0.5, y1), (13.5, y1), mark: (end: ">"))
    line((-0.5, y2), (13.5, y2), mark: (end: ">"))
    line((-0.5, y3), (13.5, y3), mark: (end: ">"))

    content((13.7, y1), [$P_A$], anchor: "west")
    content((13.7, y2), [$P_B$], anchor: "west")
    content((13.7, y3), [$P_C$], anchor: "west")

    // CS labels
    content(((p1-cs-start + p1-cs-end) / 2, y1 + 0.3), [CS], anchor: "south")
    content(((p2-cs-start + p2-cs-end) / 2, y2 + 0.3), [CS], anchor: "south")
    content(((p3-cs-start + p3-cs-end) / 2, y3 + 0.3), [CS], anchor: "south")

    let events = (
      // === REQUESTS ===
      (req-send, y1, $a_1$, "south"),
      (req-send, y2, $b_1$, "north"),
      (req-send, y3, $c_1$, "north"),

      (req-p1-from-p2, y1, $a_2$, "south"),
      (req-p1-from-p3, y1, $a_3$, "south"),
      (req-p2-from-p1, y2, $b_2$, "north"),
      (req-p2-from-p3, y2, $b_3$, "south"),
      (req-p3-from-p1, y3, $c_2$, "north"),
      (req-p3-from-p2, y3, $c_3$, "north"),

      // === ACKS ===
      (ack-send1, y1, $a_4$, "south"),
      (ack-send1, y2, $b_4$, "north"),
      (ack-send1, y3, $c_4$, "north"),
      (ack-send2, y1, $a_5$, "south"),
      (ack-send2, y2, $b_5$, "north"),
      (ack-send2, y3, $c_5$, "north"),

      (ack-p1-from-p2, y1, $a_6$, "south"),
      (ack-p1-from-p3, y1, $a_7$, "south"),
      (ack-p2-from-p1, y2, $b_6$, "north"),
      (ack-p2-from-p3, y2, $b_7$, "south"),
      (ack-p3-from-p1, y3, $c_6$, "north"),
      (ack-p3-from-p2, y3, $c_7$, "north"),

      // === P1 RELEASE ===
      (p1-rel-send,    y1, $a_8$, "south"),
      (p1-rel-p2-recv, y2, $b_8$, "north"),
      (p1-rel-p3-recv, y3, $c_8$, "north"),

      // === P2 RELEASE ===
      (p2-rel-send,    y2, $b_9$, "north"),
      (p2-rel-p1-recv, y1, $a_9$, "south"),
      (p2-rel-p3-recv, y3, $c_9$, "north"),

      // === P3 RELEASE ===
      (p3-rel-send,    y3, $c_10$, "north"),
      (p3-rel-p1-recv, y1, $a_10$, "south"),
      (p3-rel-p2-recv, y2, $b_10$, "south"),
    )

    let arrows = (
      // === REQUEST ARROWS ===
      ((req-send, y1), (req-p2-from-p1, y2), green),
      ((req-send, y1), (req-p3-from-p1, y3), green),
      ((req-send, y2), (req-p1-from-p2, y1), green),
      ((req-send, y2), (req-p3-from-p2, y3), green),
      ((req-send, y3), (req-p1-from-p3, y1), green),
      ((req-send, y3), (req-p2-from-p3, y2), green),

      // === ACK ARROWS ===
      ((ack-send1, y1), (ack-p2-from-p1, y2), orange),
      ((ack-send2, y1), (ack-p3-from-p1, y3), orange),
      ((ack-send1, y2), (ack-p1-from-p2, y1), orange),
      ((ack-send2, y2), (ack-p3-from-p2, y3), orange),
      ((ack-send1, y3), (ack-p1-from-p3, y1), orange),
      ((ack-send2, y3), (ack-p2-from-p3, y2), orange),

      // === RELEASE ARROWS ===
      ((p1-rel-send, y1), (p1-rel-p2-recv, y2), blue),
      ((p1-rel-send, y1), (p1-rel-p3-recv, y3), blue),
      ((p2-rel-send, y2), (p2-rel-p1-recv, y1), blue),
      ((p2-rel-send, y2), (p2-rel-p3-recv, y3), blue),
      ((p3-rel-send, y3), (p3-rel-p1-recv, y1), blue),
      ((p3-rel-send, y3), (p3-rel-p2-recv, y2), blue),
    )

    for (from, to, color) in arrows {
      line(from, to, mark: (end: ">", size: 0.2), stroke: color)
    }

    for (x, y, lbl, anch) in events {
      circle((x, y), radius: 0.07, fill: black)
      content((x, y), lbl, anchor: anch, padding: 0.12)
    }
  }),
  caption: [Lamport's Mutual Exclusion mit drei Prozessen ($P_1 < P_2 < P_3$ bei Gleichstand)\ $forall e_i in E : C(e_i) = i$ \
  Grüne Pfeile repräsentieren Requests, orange Pfeile Acknowledgements, blaue Pfeile Releases.],
)
]
Relevante Warteschlangen-Veränderungen:
$
  a_1 &: [(A, 1)] \
  b_1 &: [(B, 1)] \
  c_1 &: [(C, 1)] \
  a_2 &: [(A, 1), (B, 1)] \
  b_2 &: [(A, 1), (B, 1)] \
  c_2 &: [(A, 1), (C, 1)] \
  a_3 = b_3 = c_3 &: [(A, 1), (B, 1), (C, 1)] \
  a_8 = b_8 = c_8 &: [(B, 1), (C, 1)] \
  a_9 = b_9 = c_9 &: [(C, 1)] \
  a_10 = b_10 = c_10 &: []
$

=== Delta-Kompression

Hier kann klassisches "Delta-Encoding" verwendet werden. Dazu wird die element-weise Differenz zwischen zwei Vektoren gebildet:

$
  delta : ZZ^n times ZZ^n -> ZZ^n | n in NN^+ \
  delta(arrow(v)_a, arrow(v)_b) = arrow(v)_b - arrow(v)_a\
$

Aus einem Anfangsvektor und einer Sequenz von beliebig vielen Delta-Vektoren kann jedes Zwischenergebnis sukzessive berechnet werden. Es geht also keine Information verloren:

$
  arrow(v)_b = arrow(v)_a + delta(arrow(v)_a, arrow(v)_b) \
  arrow(V) = [arrow(v)_0, arrow(v)_1, dots, arrow(v)_n] \
  arrow(D) = [delta(arrow(v)_0, arrow(v)_1), delta(arrow(v)_1, arrow(v)_2), dots, delta(arrow(v)_(n-1), arrow(v)_n)] \
  arrow(v)_i = arrow(v)_0 + sum_(j=1)^i arrow(D)_j
$

An einem Beispiel:

$
  arrow(v)_1 = vec(100000, 200000, 300000)
  wide
  arrow(v)_2 = vec(100005, 200005, 300005)
  wide
  arrow(v)_d = delta(arrow(v)_1, arrow(v)_2) = vec(5, 5, 5)
$

Liegen die Eingabevektoren nahe beieinander, haben die daraus resultierenden Vektoren deutlich kleinere Werte. Das Speichern/Verschicken der Delta-Vektoren benötigt also deutlich weniger Bits als die absoluten. Es wird nur ein einziger kompletter Vektor benötigt. Dieses Konzept ist bei verteilten Zeitsystemen sehr sinnvoll, da davon ausgegangen wird, dass der Clock Drift zwischen Teilnehmern nicht gigantisch ist. Daher liegen die Vektoren im Schnitt recht nah beieinander. Unter der Annahme, dass vorzeichelose Ganzzahlen (z.B. Unix-Zeitstempel) kodiert werden und die Zeitstempel monoton steigend sind (also auch die Deltavektoren immer positiv sind) verbraucht der Deltavektor deutlich weniger Platz bei der Übertragung:

$
  "bitlen"(n) := cases(
    1 &| n = 0,
    ceil(log_2 n) &| n in NN^+
  ) \

  "bitlen"(arrow(v)) := sum_(i=1)^(n) "bitlen"(v_i) | arrow(v) in NN^n \

  "bitlen"(arrow(v)_2) = 54 \
  "bitlen"(arrow(v)_d) = 9
$
