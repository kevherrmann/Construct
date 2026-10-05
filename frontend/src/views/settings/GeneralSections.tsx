import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import type { Lang, Settings } from '@/lib/bootstrap'
import { useSettings } from '@/stores/settings'
import { Section } from './parts'
import s from './Settings.module.css'

export function LanguageSection() {
  const { t } = useTranslation()
  const boot = useSettings((st) => st.boot.lang)
  const save = useSettings((st) => st.save)
  // Die neue Wahl bleibt sichtbar, während gespeichert und neu geladen wird.
  const [lang, setLang] = useState<Lang>(boot)
  // Neu laden statt live umschalten: Texte stecken auch in schon gebauten
  // Ansichten und im Server-Prompt — ein frischer Start ist die ehrliche Lösung.
  const change = async (v: Lang) => {
    setLang(v)
    await save({ lang: v })
    location.reload()
  }
  return (
    <Section id="sprache">
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.d}>
            {t('Sprache der Oberfläche und des Assistenten. Die Seite lädt danach neu.')}
          </span>
          <span className={s.actions}>
            <select
              className={s.btn}
              translate="no"
              value={lang}
              onChange={(e) => void change(e.target.value as Lang)}
            >
              <option value="en">English</option>
              <option value="de">Deutsch</option>
            </select>
          </span>
        </span>
      </div>
    </Section>
  )
}

type Tile = keyof Settings['tiles']
// Als Funktion mit t()-Aufrufen, damit der Übersetzungstest die Texte sieht.
const tileList = (t: TFunction): { k: Tile; i: string; label: string; d: string }[] => [
  {
    k: 'tickets',
    i: '🎫',
    label: t('Tickets'),
    d: t(
      'Gliedert eine Session in Aufgaben: Chip über der Eingabe, /ticket und diese Übersicht. Aus = es wird nichts mitgeschrieben.',
    ),
  },
  {
    k: 'kalender',
    i: '📅',
    label: t('Kalender'),
    d: t('Termine eintragen und ansehen. Braucht nichts weiter.'),
  },
  {
    k: 'skills',
    i: '⚡',
    label: t('Skills'),
    d: t('Zeigt die Skills aus deinen Projekten. Nur mit Claude Code sinnvoll.'),
  },
  {
    k: 'mail',
    i: '📧',
    label: t('E-Mails'),
    d: t('Postfach über IMAP/SMTP. Zugangsdaten liegen lokal.'),
  },
  {
    k: 'mcp',
    i: '🔌',
    label: t('MCP'),
    d: t('Zeigt konfigurierte MCP-Server. Nur mit Claude Code sinnvoll.'),
  },
]

// Der Chat hat bewusst keinen Schalter: eine Oberfläche ohne ihren Hauptzweck
// wäre eine Sackgasse, aus der man nicht zurückfindet.
export function TilesSection() {
  const { t } = useTranslation()
  const tiles = useSettings((st) => st.settings.tiles)
  const save = useSettings((st) => st.save)
  return (
    <Section id="kacheln">
      <div className={s.row}>
        <label style={{ cursor: 'default' }}>
          <input type="checkbox" checked disabled />
          <span>
            <span className={s.t}>💬 {t('Chats')}</span>
            <span className={s.d}>
              {t('Der Hauptzweck der Oberfläche — lässt sich nicht abschalten.')}
            </span>
          </span>
        </label>
        <span className={s.fixed}>{t('FEST')}</span>
      </div>
      {tileList(t).map((x) => (
        <div className={s.row} key={x.k}>
          <label>
            <input
              type="checkbox"
              checked={tiles[x.k] !== false}
              onChange={(e) => void save({ tiles: { [x.k]: e.target.checked } })}
            />
            <span>
              <span className={s.t}>
                {x.i} {x.label}
              </span>
              <span className={s.d}>{x.d}</span>
            </span>
          </label>
        </div>
      ))}
    </Section>
  )
}

// Der Team-Modus: eine Firma aus KI-Mitarbeitern neben dem einzelnen Assistenten.
// Aus = CONSTRUCT ist, was es war: ein Assistent. An = es gibt Belegschaft und
// Aufträge, und je Aufgabe lässt sich entscheiden, ob nur der Assistent arbeitet
// oder die ganze Firma.
export function TeamSection() {
  const { t } = useTranslation()
  const team = useSettings((st) => st.settings.team)
  const tickets = useSettings((st) => st.settings.tickets)
  const save = useSettings((st) => st.save)
  return (
    <Section id="team">
      <div className={s.row}>
        <label>
          <input
            type="checkbox"
            checked={team.aktiv}
            onChange={(e) => void save({ team: { aktiv: e.target.checked } })}
          />
          <span>
            <span className={s.t}>🏢 {t('Team-Modus')}</span>
            <span className={s.d}>
              {t(
                'Eine Firma aus KI-Mitarbeitern: Personal und Aufträge. Große Aufgaben gibst du an die Firma, kleine erledigt der Assistent allein. Aus = alles wie bisher.',
              )}
            </span>
          </span>
        </label>
      </div>
      {team.aktiv && (
        <div className={s.row}>
          <span className={s.grow}>
            <span className={s.t}>{t('Wer entscheidet, was an die Firma geht?')}</span>
            <span className={s.actions}>
              {(['zuruf', 'auto'] as const).map((m) => (
                <label key={m}>
                  <input
                    type="radio"
                    name="team-modus"
                    checked={team.modus === m}
                    onChange={() => void save({ team: { modus: m } })}
                  />
                  <span>
                    <span className={s.t}>
                      {m === 'zuruf' ? t('Nur auf Zuruf') : t('Der Assistent darf vorschlagen')}
                    </span>
                    <span className={s.d}>
                      {m === 'zuruf'
                        ? t('/firma, der Knopf am Ticket oder deine ausdrückliche Bitte.')
                        : t('Bei großen Aufgaben schlägt er die Firma vor und fragt dich vorher.')}
                    </span>
                  </span>
                </label>
              ))}
            </span>
          </span>
        </div>
      )}
      <div className={s.row}>
        <label>
          <input
            type="checkbox"
            checked={tickets.assistent}
            onChange={(e) => void save({ tickets: { assistent: e.target.checked } })}
          />
          <span>
            <span className={s.t}>🎫 {t('Assistent ordnet Tickets mit')}</span>
            <span className={s.d}>
              {t(
                'Er legt neue Tickets an und ordnet Korrekturen zu — mit einer Zeile am Ende seiner Antwort, nur wenn nötig (etwa 0,5 % Mehrverbrauch). Aus = nur die automatische Zuordnung und deine eigenen Eingriffe.',
              )}
            </span>
          </span>
        </label>
      </div>
    </Section>
  )
}

// Die Konten selbst verwaltet die E-Mail-Ansicht (/mail/accounts).
export function MailSection() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const mailOff = useSettings((st) => st.settings.tiles.mail === false)
  return (
    <Section id="mail">
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.d}>
            {t(
              'Postfächer anlegen, Passwort ändern, Verbindung testen — die Konten werden in der E-Mail-Ansicht verwaltet (dort auch links unten über „Konten verwalten“).',
            )}
          </span>
          <span className={s.actions}>
            <button
              type="button"
              className={s.btn}
              disabled={mailOff}
              title={mailOff ? t('Kachel E-Mails ist abgeschaltet') : undefined}
              onClick={() => nav('/mail/accounts')}
            >
              {t('⚙ Konten verwalten…')}
            </button>
          </span>
        </span>
      </div>
    </Section>
  )
}
