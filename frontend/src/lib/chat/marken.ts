/** Die Markerzeile, mit der der Assistent eine Aufgabe an die Firma gibt
 *  (`[[firma: Titel]]`), steht ganz unten in seiner Antwort und ist nicht für die
 *  Anzeige gedacht. Der Server wertet sie beim Zugende aus (server/team/chat.py) und
 *  entfernt sie aus dem Verlauf; beim Streamen taucht die Zeile aber Zeichen für
 *  Zeichen auf, auch halb fertig. Darum wird jede letzte Zeile entfernt, die mit `[[`
 *  anfängt — ein Marker mitten im Text bleibt stehen. Ältere Verläufe enthalten noch
 *  `[[ticket …]]`-Zeilen; die fallen genauso weg. */
export const ohneMarke = (text: string): string => text.replace(/\n*[ \t]*\[\[[^\n]*$/, '')
