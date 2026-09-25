import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import type { Lang, Settings } from '@/lib/bootstrap'
import { useSettings } from '@/stores/settings'
import { Section } from './parts'
import s from './Settings.module.css'

export function LanguageSection() {
  const { t } = useTranslation()
  const lang = useSettings((st) => st.boot.lang)
  const save = useSettings((st) => st.save)
  // Neu laden statt live umschalten: Texte stecken auch in schon gebauten
  // Ansichten und im Server-Prompt — ein frischer Start ist die ehrliche Lösung.
  const change = async (v: Lang) => {
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
