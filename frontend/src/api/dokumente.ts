import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, apiPost } from '@/lib/api'

const B = '/api/dokumente'

export interface Name {
  id: number
  name: string
  anzahl: number
}

export interface Dok {
  id: number
  titel: string
  /** YYYY-MM-DD oder null. */
  datum: string | null
  absender_id: number | null
  absender: string | null
  typ_id: number | null
  typ: string | null
  tags: { id: number; name: string }[]
  datei: string | null
  seiten: number
  notiz: string
  /** true = noch nicht bestätigt (Eingang). */
  eingang: boolean
  /** lesen = Texterkennung läuft noch. */
  zustand: 'lesen' | 'fertig' | 'fehler'
  hinweis: string
  quelle: string
  hinzugefuegt: string
  geaendert: string
  text?: string
}

export interface Uebersicht {
  gesamt: number
  eingang: number
  lesen: number
  jahre: { jahr: string; anzahl: number }[]
  ohne_datum: number
  texterkennung: boolean
  scanner: boolean
}

export interface Filter {
  q: string
  jahr: string
  absender: number | null
  typ: number | null
  tag: number | null
  eingang: boolean | null
}

export interface Aenderung {
  titel?: string
  datum?: string | null
  absender?: string | number | null
  typ?: string | number | null
  tags?: (string | number)[]
  notiz?: string
  eingang?: boolean
}

export interface ScanStand {
  id: string
  zustand: 'bereit' | 'scannt' | 'stau' | 'fehler' | 'fertig'
  meldung: string
  quelle: 'einzug' | 'glas' | ''
  seite: 'vorne' | 'hinten'
  geraet: string
  farbe: boolean
  vorne: number
  hinten: number
}

export interface SicherungZiel {
  an: boolean
  letzte: string
  fehler: string
  ergebnis: string
  aktuell: boolean
}

export interface SicherungStand {
  ordner: string
  server: { host?: string; benutzer?: string; port?: number; ordner?: string; schluessel?: string }
  kennwort: boolean
  ziele: { ordner: SicherungZiel; server: SicherungZiel }
  eingerichtet: boolean
  laeuft: boolean
}

export interface SicherungEinstellung {
  ordner?: string
  server?: { host: string; benutzer: string; port: number; ordner: string; schluessel: string }
  kennwort?: string
}

export interface ProbeErgebnis {
  dateien: number
  fehlt: string[]
  fehlt_anzahl: number
  dokumente: number
  dokumente_soll: number
}

export const useSicherung = () =>
  useQuery({
    queryKey: ['dokumente', 'sicherung'],
    queryFn: () => apiGet<SicherungStand>(`${B}/sicherung`),
    refetchInterval: (q) => (q.state.data?.laeuft ? 3000 : 60_000),
  })

export const dateiUrl = (id: number, download = false) =>
  `${B}/${id}/datei${download ? '?download=1' : ''}`
export const vorschauUrl = (d: Pick<Dok, 'id' | 'geaendert' | 'zustand'>) =>
  `${B}/${d.id}/vorschau?v=${encodeURIComponent(d.geaendert)}${d.zustand}`
export const scanSeiteUrl = (sid: string, seite: 'vorne' | 'hinten', n: number) =>
  `${B}/scan/${sid}/seite/${seite}/${n}`

const parameter = (f: Filter) => {
  const p = new URLSearchParams()
  if (f.q.trim()) p.set('q', f.q.trim())
  if (f.jahr) p.set('jahr', f.jahr)
  if (f.absender) p.set('absender', String(f.absender))
  if (f.typ) p.set('typ', String(f.typ))
  if (f.tag) p.set('tag', String(f.tag))
  if (f.eingang !== null) p.set('eingang', f.eingang ? '1' : '0')
  return p.toString()
}

/** Solange etwas gelesen wird, alle paar Sekunden nachsehen. */
const nachfragen = (lesen: boolean) => (lesen ? 2500 : false)

export const useUebersicht = () =>
  useQuery({
    queryKey: ['dokumente', 'uebersicht'],
    queryFn: () => apiGet<Uebersicht>(`${B}/uebersicht`),
    refetchInterval: (q) => nachfragen(!!q.state.data?.lesen),
    // Der Assistent sortiert über doku.py ein: beim Öffnen frisch holen.
    refetchOnMount: 'always',
  })

export const useDokumente = (f: Filter) =>
  useQuery({
    queryKey: ['dokumente', 'liste', f],
    queryFn: () => apiGet<{ gesamt: number; dokumente: Dok[] }>(`${B}?${parameter(f)}`),
    placeholderData: keepPreviousData,
    refetchInterval: (q) =>
      nachfragen(!!q.state.data?.dokumente.some((d) => d.zustand === 'lesen')),
    refetchOnMount: 'always',
  })

export const useDokument = (id: number) =>
  useQuery({
    queryKey: ['dokumente', 'eins', id],
    queryFn: () => apiGet<Dok>(`${B}/${id}`),
    refetchInterval: (q) => nachfragen(q.state.data?.zustand === 'lesen'),
  })

export const useNamen = (tabelle: 'absender' | 'typen' | 'tags') =>
  useQuery({
    queryKey: ['dokumente', 'namen', tabelle],
    queryFn: () => apiGet<Name[]>(`${B}/namen/${tabelle}`),
  })

export const useScanGeraete = (an: boolean) =>
  useQuery({
    queryKey: ['dokumente', 'scanner'],
    queryFn: () =>
      apiGet<{ verfuegbar: boolean; geraete: { id: string; name: string }[] }>(`${B}/scan/geraete`),
    enabled: an,
    staleTime: 60_000,
  })

export const useScanStand = (sid: string | null) =>
  useQuery({
    queryKey: ['dokumente', 'scan', sid],
    queryFn: () => apiGet<ScanStand>(`${B}/scan/${sid}`),
    enabled: !!sid,
    refetchInterval: (q) => (q.state.data?.zustand === 'scannt' ? 1500 : false),
  })

export function useDokumenteAktionen() {
  const qc = useQueryClient()
  const fertig = () => void qc.invalidateQueries({ queryKey: ['dokumente'] })
  const useAktion = <V, R>(fn: (v: V) => Promise<R>) =>
    useMutation({ mutationFn: fn, onSuccess: fertig })
  return {
    aendern: useAktion((v: { id: number } & Aenderung) => {
      const { id, ...rest } = v
      return apiPost<Dok>(`${B}/${id}`, rest)
    }),
    loeschen: useAktion((id: number) => apiDelete<{ ok: boolean }>(`${B}/${id}`)),
    teilen: useAktion((v: { id: number; seiten: string }) =>
      apiPost<{ dokumente: Dok[] }>(`${B}/${v.id}/teilen`, { seiten: v.seiten }),
    ),
    hochladen: useAktion((file: File) => {
      const fd = new FormData()
      fd.append('datei', file)
      // Leere headers: der Browser setzt den multipart-Rand selbst.
      return apiPost<Dok>(`${B}/hochladen`, undefined, { body: fd, headers: {} })
    }),
    scanStart: useAktion(
      (v: { quelle: 'auto' | 'einzug' | 'glas'; farbe: boolean; geraet?: string }) =>
        apiPost<ScanStand>(`${B}/scan`, v),
    ),
    scanWeiter: useAktion((v: { sid: string; was: 'glas' | 'einzug' | 'rueckseiten' }) =>
      apiPost<ScanStand>(`${B}/scan/${v.sid}/weiter`, { was: v.was }),
    ),
    scanFertig: useAktion((v: { sid: string; einzeln: boolean; zuordnung?: number[] }) =>
      apiPost<{ dokumente: Dok[] }>(`${B}/scan/${v.sid}/fertig`, {
        einzeln: v.einzeln,
        zuordnung: v.zuordnung,
      }),
    ),
    scanAbbrechen: useAktion((sid: string) => apiDelete<{ ok: boolean }>(`${B}/scan/${sid}`)),
    sicherungEinrichten: useAktion((v: SicherungEinstellung) =>
      apiPost<SicherungStand>(`${B}/sicherung`, v),
    ),
    sicherungJetzt: useAktion(() => apiPost<SicherungStand>(`${B}/sicherung/jetzt`, {})),
    sicherungPruefen: useAktion((ziel: 'ordner' | 'server') =>
      apiPost<ProbeErgebnis>(`${B}/sicherung/pruefen`, { ziel }),
    ),
    umbenennen: useAktion(
      (v: { tabelle: 'absender' | 'typen' | 'tags'; id: number; name: string }) =>
        apiPost<{ ok: boolean }>(`${B}/namen/${v.tabelle}/${v.id}`, { name: v.name }),
    ),
  }
}
