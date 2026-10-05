/** Die Markerzeilen, mit denen der Assistent Tickets zuordnet (`[[ticket neu: …]]`,
 *  `[[ticket zu: 2]]`, `[[ticket firma]]`), stehen ganz unten in seiner Antwort und
 *  sind nicht für die Anzeige gedacht. Der Server wertet sie beim Zugende aus
 *  (server/tickets.py) und entfernt sie aus dem Verlauf; beim Streamen taucht die
 *  Zeile aber Zeichen für Zeichen auf, auch halb fertig. Darum wird jede letzte
 *  Zeile entfernt, die mit `[[` anfängt — ein Marker mitten im Text bleibt stehen. */
export const ohneMarke = (text: string): string => text.replace(/\n*[ \t]*\[\[[^\n]*$/, '')
