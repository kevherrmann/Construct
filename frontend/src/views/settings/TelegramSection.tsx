import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import {
  saveTelegram,
  testTelegram,
  useTelegram,
  type TelegramConf,
  type TelegramPatch,
} from '@/api/settings'
import { CLAUDE_MODELS } from '@/lib/chat/models'
import { rich } from '@/lib/rich'
import { trServer } from '@/lib/serverText'
import { useSettings } from '@/stores/settings'
import { Note, Section } from './parts'
import s from './Settings.module.css'

interface Form {
  enabled: boolean
  chat: string
  model: string
  mode: TelegramConf['mode']
  reminders: boolean
  hour: number
  lead: number
  notify: boolean
  token: string
}

const toForm = (c: TelegramConf): Form => ({
  enabled: !!c.enabled,
  chat: c.chat_id ? String(c.chat_id) : '',
  model: c.model || '',
  mode: c.mode,
  reminders: !!c.reminders,
  hour: c.reminder_hour,
  lead: c.reminder_lead,
  notify: !!c.notify,
  // Der Token geht nur einmal zum Server und kommt nie zurück.
  token: '',
})

function statusText(t: TFunction, c: TelegramConf) {
  const st = c.status ?? { state: 'off', error: '', bot: '', candidate: null }
  switch (st.state) {
    case 'off':
      return c.has_token ? t('aus') : t('noch nicht eingerichtet')
    case 'starting':
      return t('startet …')
    case 'running':
      return (
        t('läuft') +
        (st.bot ? ' — @' + st.bot : '') +
        (c.chat_id ? '' : ' · ' + t('wartet auf deine Chat-ID'))
      )
    case 'conflict':
      return t(
        '⚠ Derselbe Bot wird schon woanders abgefragt (anderer Rechner oder Server). Dort stoppen oder einen eigenen Bot anlegen.',
      )
    case 'error':
      return '⚠ ' + (trServer(st.error) || t('Fehler'))
    default:
      return String(st.state)
  }
}

// Der Status wird abgefragt, solange die Seite offen ist — so taucht die
// Chat-ID auf, sobald man dem Bot schreibt.
export function TelegramSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const assistant = useSettings((st) => st.boot.assistant)
  const q = useTelegram()
  const [form, setForm] = useState<Form | null>(null)
  const [note, setNote] = useState('')
  // Formular einmalig aus dem ersten Stand füllen; danach gilt die Eingabe.
  if (!form && q.data) setForm(toForm(q.data))
  const f = form ?? toForm(q.data ?? ({ mode: 'bypassPermissions' } as TelegramConf))
  const set = (p: Partial<Form>) => setForm({ ...f, ...p })
  const c = q.data

  const save = async (over: Partial<Form> = {}) => {
    const v = { ...f, ...over }
    setForm(v)
    const body: TelegramPatch = {
      enabled: v.enabled,
      chat_id: v.chat.trim(),
      model: v.model,
      mode: v.mode,
      reminders: v.reminders,
      reminder_hour: v.hour,
      reminder_lead: v.lead,
      notify: v.notify,
    }
    if (v.token.trim()) body.token = v.token.trim()
    setNote(t('⟲ speichere …'))
    try {
      const j = await saveTelegram(body)
      qc.setQueryData(['telegram'], j)
      setForm(toForm(j))
      setNote(t('✓ gespeichert'))
    } catch (e) {
      setNote('⚠ ' + trServer((e as Error).message))
    }
  }

  const test = async () => {
    setNote(t('⟲ sende …'))
    try {
      await testTelegram()
      setNote(t('✅ gesendet!'))
    } catch (e) {
      setNote('⚠ ' + trServer((e as Error).message))
    }
  }

  const cand = c && !c.chat_id ? c.status?.candidate : null
  const tokenPh = c?.from_env
    ? t('aus der Umgebung (TELEGRAM_TOKEN)')
    : c?.has_token
      ? t('•••••••• (gespeichert — nur zum Ändern neu eingeben)')
      : '123456789:AA…'

  return (
    <Section id="telegram">
      <div className={s.d} style={{ marginBottom: 10 }}>
        {t(
          'Sprich mit {a} von unterwegs — per Text oder Sprachnachricht. Dazu Erinnerungen an Termine, eine Meldung, wenn ein langer Lauf fertig ist, und geplante Aufgaben aus dem Kalender. Läuft nur, solange CONSTRUCT läuft.',
          { a: assistant },
        )}
      </div>
      <div className={s.row}>
        <label>
          <input
            type="checkbox"
            checked={f.enabled}
            onChange={(e) => void save({ enabled: e.target.checked })}
          />
          <span>
            <span className={s.t}>{t('Telegram-Bot aktiv')}</span>
            <span className={s.d}>{c ? statusText(t, c) : '…'}</span>
          </span>
        </label>
      </div>
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.t}>{t('Bot-Token')}</span>
          <span className={s.d}>
            {rich(
              t(
                'In Telegram bei <b>@BotFather</b>: <code>/newbot</code> → Namen vergeben → Token kopieren.',
              ),
            )}
          </span>
          <span className={s.actions} style={{ marginTop: 8 }}>
            <input
              className={s.in}
              type="password"
              autoComplete="off"
              spellCheck={false}
              style={{ width: '100%', maxWidth: 420 }}
              value={f.token}
              disabled={!!c?.from_env}
              placeholder={tokenPh}
              onChange={(e) => set({ token: e.target.value })}
            />
          </span>
        </span>
      </div>
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.t}>{t('Deine Chat-ID')}</span>
          <span className={s.d}>
            {t(
              'Nur diese ID darf mit dem Bot reden. Unbekannt? Bot aktivieren und ihm irgendetwas schreiben — dann erscheint sie hier.',
            )}
          </span>
          <span className={s.actions} style={{ marginTop: 8 }}>
            <input
              className={s.in}
              inputMode="numeric"
              spellCheck={false}
              style={{ width: 180 }}
              value={f.chat}
              onChange={(e) => set({ chat: e.target.value })}
            />
            {cand && (
              <>
                {' '}
                <span className={`${s.d} ${s.inlineD}`}>
                  {t('Nachricht von {n} ({id})', { n: cand.name, id: cand.id })}
                </span>{' '}
                <button
                  type="button"
                  className={s.btn}
                  onClick={() => void save({ chat: String(cand.id) })}
                >
                  {t('Übernehmen')}
                </button>
              </>
            )}
          </span>
        </span>
      </div>
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.t}>{t('Modell und Modus')}</span>
          <span className={s.d}>
            {t(
              'Womit der Bot antwortet. „Plan“ liest nur und ändert nichts — die sichere Wahl, wenn das Handy mal in fremde Hände gerät.',
            )}
          </span>
          <span className={s.actions} style={{ marginTop: 8 }}>
            <select
              className={s.btn}
              value={f.model}
              onChange={(e) => set({ model: e.target.value })}
            >
              {CLAUDE_MODELS.map((m) => (
                <option key={m.v} value={m.v}>
                  {m.v ? m.l : t('Standard')}
                </option>
              ))}
            </select>
            <select
              className={s.btn}
              value={f.mode}
              onChange={(e) => set({ mode: e.target.value as Form['mode'] })}
            >
              <option value="bypassPermissions">⚡ Auto</option>
              <option value="plan">📋 Plan</option>
            </select>
          </span>
        </span>
      </div>
      <div className={s.row}>
        <label>
          <input
            type="checkbox"
            checked={f.reminders}
            onChange={(e) => set({ reminders: e.target.checked })}
          />
          <span>
            <span className={s.t}>{t('Erinnerungen an Termine')}</span>
            <span className={s.d}>
              {t('Morgens eine Übersicht über den Tag, vor terminierten Einträgen ein Ping.')}
            </span>
          </span>
        </label>
        <span style={{ display: 'block', margin: '8px 0 0 30px' }}>
          <select className={s.btn} value={f.hour} onChange={(e) => set({ hour: +e.target.value })}>
            {Array.from({ length: 24 }, (_, h) => (
              <option key={h} value={h}>
                {t('Übersicht um {h} Uhr', { h: String(h).padStart(2, '0') + ':00' })}
              </option>
            ))}
          </select>
          <select className={s.btn} value={f.lead} onChange={(e) => set({ lead: +e.target.value })}>
            <option value={0}>{t('kein Ping vorher')}</option>
            <option value={10}>{t('10 Min vorher')}</option>
            <option value={15}>{t('15 Min vorher')}</option>
            <option value={30}>{t('30 Min vorher')}</option>
            <option value={60}>{t('60 Min vorher')}</option>
          </select>
        </span>
      </div>
      <div className={s.row}>
        <label>
          <input
            type="checkbox"
            checked={f.notify}
            onChange={(e) => set({ notify: e.target.checked })}
          />
          <span>
            <span className={s.t}>{t('Melden, wenn ein langer Lauf fertig ist')}</span>
            <span className={s.d}>{t('Nur wenn gerade niemand im Fenster zuschaut.')}</span>
          </span>
        </label>
      </div>
      <div className={s.actionsFlex}>
        <button type="button" className={s.btn} onClick={() => void save()}>
          {t('Speichern')}
        </button>
        <button type="button" className={s.btn} onClick={() => void test()}>
          {t('Test-Nachricht')}
        </button>
        <Note text={note} />
      </div>
    </Section>
  )
}
