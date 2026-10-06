import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAgent, useAgentActions, useBelegschaft, type Agent } from '@/api/team'
import { EFFORTS, MODELLE, MODI, WERKZEUGE } from '@/lib/team'
import { Avatar } from './Person'
import { usePersonal } from './store'
import s from './Personal.module.css'

interface Entwurf {
  name: string
  title: string
  reports_to: string
  model: string
  effort: string
  model_grund: string
  permission_mode: string
  cwd: string
  allowed_tools: string[]
  can_delegate: boolean
  stille_min: string
  soul: string
  memory: string
}

const ausAkte = (a: Agent): Entwurf => ({
  name: a.name,
  title: a.title,
  reports_to: a.reports_to,
  model: a.model,
  effort: a.effort,
  model_grund: a.model_grund,
  permission_mode: a.permission_mode,
  cwd: a.cwd,
  allowed_tools: a.allowed_tools,
  can_delegate: a.can_delegate,
  stille_min: String(Math.round(a.max_stille_s / 60)),
  soul: a.soul,
  memory: a.memory,
})

/** Eine Zeile des Formulars: Beschriftung links, Feld rechts. */
function Zeile({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className={s.fr}>
      <label>{label}</label>
      <div className={s.feld}>{children}</div>
    </div>
  )
}

/** Die Personalakte: alles, was ein Mitarbeiter ist und darf. Der Server prüft beim
 *  Speichern noch einmal — was er beanstandet, hat er korrigiert, und das steht
 *  danach hier, sonst wundert man sich später. */
function Formular({ a }: { a: Agent }) {
  const { t } = useTranslation()
  const slug = a.slug
  const zeigeOrg = usePersonal((st) => st.zeigeOrg)
  const { data: bel } = useBelegschaft()
  const act = useAgentActions()
  const [e, setE] = useState<Entwurf>(() => ausAkte(a))
  // Der Stand, den der Server zuletzt kannte — Grundlage für „was habe ich geändert“.
  const [basis, setBasis] = useState<Entwurf>(() => ausAkte(a))
  const [msg, setMsg] = useState<{ text: string; warn?: boolean }>({ text: '' })
  const set = <K extends keyof Entwurf>(k: K, v: Entwurf[K]) =>
    setE((x) => (x ? { ...x, [k]: v } : x))

  // Gesendet wird nur, was DU geändert hast. Das Gedächtnis schreibt auch der Mitarbeiter
  // selbst, während die Akte offen ist; ein blindes Zurückschreiben des Formulars würde
  // seine neuen Einträge überschreiben.
  const speichern = () => {
    setMsg({ text: `⟲ ${t('speichere …')}` })
    const neu: Record<string, unknown> = { slug }
    const alt = basis
    const d = e
    if (d.name !== alt.name) neu.name = d.name
    if (d.title !== alt.title) neu.title = d.title
    if (d.reports_to !== alt.reports_to) neu.reports_to = d.reports_to
    if (d.model !== alt.model) neu.model = d.model
    if (d.effort !== alt.effort) neu.effort = d.effort
    if (d.model_grund !== alt.model_grund) neu.model_grund = d.model_grund
    if (d.permission_mode !== alt.permission_mode) neu.permission_mode = d.permission_mode
    if (d.cwd !== alt.cwd) neu.cwd = d.cwd
    if (d.allowed_tools.join() !== alt.allowed_tools.join())
      neu.allowed_tools = d.allowed_tools.join(', ')
    if (d.can_delegate !== alt.can_delegate) neu.can_delegate = d.can_delegate
    if (d.stille_min !== alt.stille_min)
      neu.max_stille_s = Math.round((Number(d.stille_min) || 30) * 60)
    if (d.soul !== alt.soul) neu.soul = d.soul
    if (d.memory !== alt.memory) neu.memory = d.memory
    act.speichern.mutate(neu as { slug: string }, {
      onSuccess: (j) => {
        // Was der Server korrigiert hat, steht danach im Formular.
        const frisch = ausAkte(j.agent)
        setE(frisch)
        setBasis(frisch)
        setMsg(
          j.problems.length
            ? {
                text: `⚠ ${t('gespeichert, aber korrigiert:')} ${j.problems.join('; ')}`,
                warn: true,
              }
            : { text: `✓ ${t('gespeichert')}` },
        )
      },
      onError: () => setMsg({ text: t('Fehler beim Speichern'), warn: true }),
    })
  }

  // Bild: eigener Sofort-Speicherweg, nicht über SPEICHERN — ein Bild auszuwählen
  // und dann zu vergessen zu speichern wäre ärgerlich.
  const bildWaehlen = () => {
    const inp = document.createElement('input')
    inp.type = 'file'
    inp.accept = 'image/*'
    inp.onchange = async () => {
      const f = inp.files?.[0]
      if (!f) return
      const fd = new FormData()
      fd.append('file', f)
      try {
        const j = (await (await fetch('/api/upload', { method: 'POST', body: fd })).json()) as {
          url?: string
          error?: string
        }
        if (!j.url) return alert(j.error ?? t('Upload fehlgeschlagen'))
        act.speichern.mutate({ slug, avatar: j.url })
      } catch {
        alert(t('Upload fehlgeschlagen'))
      }
    }
    inp.click()
  }

  const bosse = (bel?.agents ?? []).filter((x) => x.slug !== slug)
  return (
    <div className={s.wrap}>
      <h2 className={s.h2} style={{ color: `rgb(${a.color})` }}>
        👤 {a.name}
        <button type="button" className={s.zurueck} onClick={zeigeOrg}>
          ← {t('Organigramm')}
        </button>
      </h2>
      {a.problems.length > 0 && (
        <div className={s.fehler}>
          ⚠ {t('An dieser Akte stimmt etwas nicht:')}
          <br />
          {a.problems.map((p) => (
            <div key={p}>{p}</div>
          ))}
        </div>
      )}
      <div className={s.akte} style={{ ['--accent-rgb' as string]: a.color }}>
        <Zeile label={t('BILD')}>
          <span className={s.bildzeile}>
            <Avatar p={a} groesse={44} />
            <button type="button" className={s.knopf} onClick={bildWaehlen}>
              {t('Bild wählen …')}
            </button>
            {a.avatar && (
              <button
                type="button"
                className={s.knopf}
                onClick={() => act.speichern.mutate({ slug, avatar: '' })}
              >
                ✕
              </button>
            )}
            <span className={s.leise}>
              {t('erscheint neben seinen Nachrichten; ohne Bild der Anfangsbuchstabe')}
            </span>
          </span>
        </Zeile>
        <Zeile label={t('NAME')}>
          <input value={e.name} maxLength={40} onChange={(x) => set('name', x.target.value)} />
        </Zeile>
        <Zeile label={t('ROLLE')}>
          <input value={e.title} maxLength={60} onChange={(x) => set('title', x.target.value)} />
        </Zeile>
        <Zeile label={t('BERICHTET AN')}>
          <select value={e.reports_to} onChange={(x) => set('reports_to', x.target.value)}>
            <option value="">{t('— niemand (Geschäftsführung) —')}</option>
            {bosse.map((b) => (
              <option key={b.slug} value={b.slug}>
                {b.name}
              </option>
            ))}
          </select>
        </Zeile>
        <Zeile label={t('MODELL')}>
          <select value={e.model} onChange={(x) => set('model', x.target.value)}>
            {Object.entries(MODELLE).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </Zeile>
        <Zeile label={t('EFFORT')}>
          <select value={e.effort} onChange={(x) => set('effort', x.target.value)}>
            {EFFORTS.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </Zeile>
        <div className={s.hinweis}>
          {t(
            'Effort bestimmt, wie gründlich das Modell nachdenkt. Recherche und mechanisches Prüfen kommen mit „low“ aus, sonst gilt „xhigh“.',
          )}
        </div>
        <Zeile label={t('WARUM DIESES MODELL?')}>
          <input
            value={e.model_grund}
            maxLength={200}
            placeholder={t('ein Satz — damit die Wahl nachvollziehbar bleibt')}
            onChange={(x) => set('model_grund', x.target.value)}
          />
        </Zeile>
        <Zeile label={t('BERECHTIGUNG')}>
          <select
            value={e.permission_mode}
            onChange={(x) => set('permission_mode', x.target.value)}
          >
            {MODI.map((m) => (
              <option key={m.v} value={m.v}>
                {t(m.l)}
              </option>
            ))}
          </select>
        </Zeile>
        <div className={s.hinweis}>
          {t(
            'Die Werkzeuge unten sind die Erlaubnis — was dort nicht steht, geht nicht. Ausnahme: acceptEdits lässt Dateiänderungen auch dann zu, wenn Write und Edit nicht angehakt sind. Wer wirklich nichts verändern soll, braucht auto.',
          )}
        </div>
        <Zeile label={t('ARBEITET IN')}>
          <input value={e.cwd} onChange={(x) => set('cwd', x.target.value)} />
        </Zeile>
        <Zeile label={t('WERKZEUGE')}>
          <span className={s.haken}>
            {WERKZEUGE.map((w) => (
              <label key={w}>
                <input
                  type="checkbox"
                  checked={e.allowed_tools.includes(w)}
                  onChange={(x) =>
                    set(
                      'allowed_tools',
                      x.target.checked
                        ? [...e.allowed_tools, w]
                        : e.allowed_tools.filter((y) => y !== w),
                    )
                  }
                />{' '}
                {w}
              </label>
            ))}
          </span>
        </Zeile>
        <div className={s.hinweis}>
          {t(
            'Wer kein Bash braucht, bekommt keins. Das schützt auch gegen ehrliche Fehler, nicht nur gegen Angreifer.',
          )}
        </div>
        <Zeile label={t('DARF')}>
          <span className={s.haken}>
            <label>
              <input
                type="checkbox"
                checked={e.can_delegate}
                onChange={(x) => set('can_delegate', x.target.checked)}
              />{' '}
              {t('verteilen')}
            </label>
          </span>
        </Zeile>
        <Zeile label={t('HÄNGT, WENN')}>
          <input
            style={{ maxWidth: 90 }}
            value={e.stille_min}
            onChange={(x) => set('stille_min', x.target.value)}
          />
          <span className={s.leise}>
            {t(
              'Minuten lang kein Lebenszeichen kommt. Wie lange ein Zug insgesamt arbeitet, ist egal.',
            )}
          </span>
        </Zeile>
        <Zeile
          label={
            <>
              {t('CHARAKTER')}
              <br />
              <span className={s.leise}>SOUL.md</span>
            </>
          }
        >
          <textarea
            className={s.text}
            value={e.soul}
            onChange={(x) => set('soul', x.target.value)}
          />
        </Zeile>
        <Zeile
          label={
            <>
              {t('GEDÄCHTNIS')}
              <br />
              <span className={s.leise}>MEMORY.md</span>
            </>
          }
        >
          <textarea
            className={s.text}
            style={{ minHeight: 90 }}
            placeholder={t('(leer — füllt sich beim Arbeiten)')}
            value={e.memory}
            onChange={(x) => set('memory', x.target.value)}
          />
        </Zeile>
        <div className={s.aktionen}>
          <button
            type="button"
            className={s.knopf}
            onClick={speichern}
            disabled={act.speichern.isPending}
          >
            {t('SPEICHERN')}
          </button>
          <button
            type="button"
            className={`${s.knopf} ${s.gefahr}`}
            onClick={() => {
              if (
                confirm(
                  `${t('{n} entlassen?', { n: a.name })}\n\n${t('Die Akte bleibt erhalten (Status „fired“), damit alte Aufträge lesbar bleiben. Du kannst sie in der Datei wieder auf „active“ setzen.')}`,
                )
              )
                act.entlassen.mutate(slug, { onSuccess: zeigeOrg })
            }}
          >
            {t('entlassen')}
          </button>
          <span className={s.msg} style={msg.warn ? { color: '#ffd24a' } : undefined}>
            {msg.text}
          </span>
        </div>
      </div>
    </div>
  )
}

/** Die Akte lädt erst, dann zeigt das Formular sie — mit der Person als Schlüssel,
 *  damit ein Wechsel das Formular neu aufbaut und Tippen nie von einem Nachladen
 *  überschrieben wird. */
export function Akte({ slug }: { slug: string }) {
  const { data: a } = useAgent(slug)
  if (!a || a.slug !== slug) return <div className={s.wrap}>⟲ …</div>
  return <Formular key={a.slug} a={a} />
}
