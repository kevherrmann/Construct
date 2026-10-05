import type { Auftrag, Nachricht } from '@/api/team'

export interface Knoten {
  slug: string
  von: string | null
  kinder: Knoten[]
  /** Hat gerade einen Zug laufen. */
  arbeitet: boolean
  /** An wen er zuletzt geliefert hat (leer = noch nicht). */
  geliefert: string
  /** Hat noch kein Wort gesagt — beauftragt, aber noch nicht dran gewesen. */
  stumm: boolean
}

/** Wer hat wen beauftragt — als Baum, nicht als Liste.
 *
 *  Die Kanten stehen im Verlauf: jede `auftrag`- und `frage`-Nachricht ist eine
 *  Linie von A nach B. Wurzel ist die Geschäftsführung. Wer von mehreren
 *  beauftragt wurde, hängt an dem, der ihn ZUERST geholt hat — sonst wäre es
 *  kein Baum mehr. */
export function besetzung(t: Auftrag, verlauf: Nachricht[], arbeitet: string): Knoten {
  const knoten = new Map<string, Knoten>()
  const reihenfolge: string[] = []
  const dazu = (slug: string, von: string | null) => {
    if (!slug || slug === 'kevin' || knoten.has(slug)) return
    knoten.set(slug, {
      slug,
      von: von && von !== 'kevin' ? von : null,
      kinder: [],
      arbeitet: false,
      geliefert: '',
      stumm: true,
    })
    reihenfolge.push(slug)
  }
  dazu(t.owner, null)
  for (const e of verlauf) if (e.an && (e.art === 'auftrag' || e.art === 'frage')) dazu(e.an, e.von)
  for (const slug of reihenfolge) {
    const k = knoten.get(slug)!
    k.arbeitet = arbeitet === slug
    const raus = [...verlauf].reverse().find((e) => e.von === slug && e.art === 'ergebnis')
    k.geliefert = raus?.an ?? ''
    k.stumm = !verlauf.some((e) => e.von === slug)
    const eltern = k.von ? knoten.get(k.von) : undefined
    if (eltern && k.von !== slug) eltern.kinder.push(k)
  }
  return knoten.get(t.owner)!
}
