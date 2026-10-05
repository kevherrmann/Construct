# Welches Modell für welche Arbeit

Zwei Schrauben, nicht eine: **Modell** und **Effort**. Die zweite wird gern
übersehen — Vorgabe wäre `xhigh`, das ist für Routinearbeit Verschwendung.

| Modell | Eingabe $/1M | Ausgabe $/1M | Kontext |
|---|---|---|---|
| `fable` | 10,00 | 50,00 | 1M |
| `opus` | 5,00 | 25,00 | 1M |
| `sonnet` | 2,00 | 10,00 | 1M |
| `haiku` | 1,00 | 5,00 | **200K** |

Zwischen oben und unten liegt **Faktor 10**.

## Zuordnung

| Art der Arbeit | Modell | Effort |
|---|---|---|
| Firmenführung, Briefings, Entscheidungen | `opus` | `high` |
| Komplexer Code, Architektur | `opus` | `xhigh` |
| Normale Umsetzung (Frontend, Backend) | `sonnet` | `high` |
| Code gegenlesen, Review | `sonnet` | `high` |
| Recherche, Doku lesen, zusammenfassen | `sonnet` | `low` |
| Tests starten, Ausgaben prüfen, Protokollieren | `haiku` | `low` |
| Gespräch, Kalender, E-Mail | `sonnet` | `medium` |

**`fable` bekommt vorerst niemand.** Doppelt so teuer wie `opus`. Wenn, dann
als bewusste Einzelentscheidung für einen konkreten schweren Auftrag — nicht
als Merkmal einer Stelle.

## Zwei Regeln, die häufig falsch gemacht werden

**Das stärkere Modell auf niedrigem Effort schlägt oft das schwächere auf
hohem.** Bevor jemand auf `haiku` gesetzt wird, ist `sonnet` + `low` die erste
Alternative — meist billiger *und* besser.

**Gemessen wird pro erledigter Aufgabe, nicht pro Anfrage.** Wer dreimal
nachfragen muss, ist nicht billig — jede Nachfrage schiebt den Auftrag näher an
die Bremsen. Ein zu sparsam besetzter
Gegenleser kostet mehr als ein teurerer, der es einmal richtig macht.

## Haiku hat nur 200K Kontext

Alle anderen 1M. Für kurze, abgegrenzte Züge egal; für alles Ausufernde nicht.
