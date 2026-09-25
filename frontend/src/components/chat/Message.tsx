import { trServer } from '@/lib/serverText'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { Block, BotItem, ChatItem, NoteText, SysBody, UserItem } from '@/lib/chat/types'
import { fmtDur, fmtNum, isPdf } from '@/lib/format'
import { useChat } from '@/stores/chat'
import { say, stopSay, useSayState } from '@/lib/audio'
import { speakableText } from '@/lib/chat/speak'
import { useSettings } from '@/stores/settings'
import { Markdown } from './Markdown'
import { ToolBox } from './ToolBox'
import s from './Message.module.css'

function useNote() {
  const { t } = useTranslation()
  return (n: NoteText) => t(n.key, n.params)
}

function Avatar({ user }: { user: boolean }) {
  const { t } = useTranslation()
  const avatars = useSettings((st) => st.settings.avatars)
  const userName = useSettings((st) => st.boot.user || st.settings.names.user)
  const img = user ? avatars.user : avatars.assistant || '/static/cody.png'
  // Ohne eigenes Foto steht der Anfangsbuchstabe im Kreis — ein leerer Kreis
  // sähe aus, als wäre ein Bild kaputt.
  return (
    <div
      className={`${s.avatar} ${user ? s.avatarUser : ''}`}
      style={img ? { backgroundImage: `url("${img}")` } : undefined}
    >
      {user && !img ? (userName || t('Du')).slice(0, 1).toUpperCase() : null}
    </div>
  )
}

function SayButton({ id, text }: { id: string; text: () => string }) {
  const { t } = useTranslation()
  const { owner, phase, error } = useSayState()
  const mine = owner === id && phase !== 'idle'
  const err = error?.owner === id ? trServer(error.message) : null
  const click = () => (mine ? stopSay() : void say(text(), { owner: id }).catch(() => {}))
  return (
    <button
      type="button"
      className={`${s.say} ${mine ? s.sayOn : ''}`}
      title={err ?? t('Vorlesen')}
      onClick={click}
    >
      {err ? '⚠' : mine ? (phase === 'loading' ? '⏳' : '⏹') : '🔊'}
    </button>
  )
}

function Frame({
  user,
  children,
  say,
}: {
  user: boolean
  children: ReactNode
  say?: { id: string; text: () => string }
}) {
  const assistant = useSettings((st) => st.boot.assistant)
  const userName = useSettings((st) => st.boot.user || st.settings.names.user)
  const { t } = useTranslation()
  return (
    <div className={`${s.msg} ${user ? s.user : s.bot}`}>
      <Avatar user={user} />
      <div className={s.col}>
        <div className={s.who}>
          {(user ? userName || t('Du') : assistant).toUpperCase()}
          {say && <SayButton {...say} />}
        </div>
        {children}
      </div>
    </div>
  )
}

function Attachments({ urls }: { urls: string[] }) {
  return (
    <>
      {urls.map((u) =>
        isPdf(u) ? (
          <a key={u} className={s.att} href={u} target="_blank" rel="noreferrer">
            📄 PDF
          </a>
        ) : (
          <img key={u} src={u} alt="" />
        ),
      )}
    </>
  )
}

// Eigene Nachricht bearbeiten & neu senden — spart Tokens, wenn man Cody
// gestoppt hat und den Auftrag nur korrigieren will.
function UserMessage({ item, busy }: { item: UserItem; busy: boolean }) {
  const { t } = useTranslation()
  const resend = useChat((st) => st.resend)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(item.text)
  const ta = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = ta.current
    if (!editing || !el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 300)}px`
  }, [editing, draft])
  useEffect(() => {
    if (!editing) return
    const el = ta.current
    el?.focus()
    el?.setSelectionRange(el.value.length, el.value.length)
  }, [editing])

  const submit = () => {
    setEditing(false)
    if (draft.trim() && !busy) resend(item.id, draft)
  }
  return (
    <Frame user>
      <div className={s.bubble}>
        {editing ? (
          <>
            <textarea
              ref={ta}
              className={s.editbox}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  e.preventDefault()
                  setEditing(false)
                } else if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  submit()
                }
              }}
            />
            <div className={s.editbar}>
              <button type="button" className={s.ebCancel} onClick={() => setEditing(false)}>
                {t('Abbrechen')}
              </button>
              <button type="button" className={s.ebSend} onClick={submit}>
                {t('↺ Neu senden')}
              </button>
            </div>
          </>
        ) : (
          <>
            <Markdown text={item.text} />
            <Attachments urls={item.urls} />
            {item.editable && !busy && (
              <button
                type="button"
                className={s.edit}
                title={t('Bearbeiten & neu senden')}
                onClick={() => {
                  setDraft(item.text)
                  setEditing(true)
                }}
              >
                ✎
              </button>
            )}
          </>
        )}
      </div>
    </Frame>
  )
}

function BlockView({ block }: { block: Block }) {
  const { t } = useTranslation()
  const note = useNote()
  switch (block.t) {
    case 'text':
      return <Markdown className={s.seg} text={block.text} streaming={block.streaming} />
    case 'thinkmark':
      return <div className={s.thinkmark}>{t('💭 nachgedacht')}</div>
    case 'tool':
      return <ToolBox block={block} />
    case 'skill':
      return (
        <div className={s.skill}>
          🧠 <b>{block.kind === 'used' ? t('Skill genutzt') : t('Skill gespeichert')}</b>
          {block.label ? (
            <>
              : <span>{block.label}</span>
            </>
          ) : null}
        </div>
      )
    case 'stats':
      return (
        <div
          className={s.statline}
          title={t(
            'Dauer · Output-Tokens dieser Antwort · gelesener Kontext (großteils Cache) · Modell',
          )}
        >
          ⏱ {fmtDur(block.durationMs)} · 🧮 {fmtNum(block.out)} Tokens
          {block.ctx ? ` · 📚 ${t('Kontext')} ${fmtNum(block.ctx)}` : ''}
          {block.model ? ` · 🧠 ${block.model}` : ''}
        </div>
      )
    case 'files':
      return (
        <div className={`${s.statline} ${s.files}`}>
          📁{' '}
          {block.paths.map((fp, i) => (
            <span key={fp}>
              {i > 0 && ' · '}
              <a
                href={`/api/file?path=${encodeURIComponent(fp)}`}
                target="_blank"
                rel="noreferrer"
                title={fp}
              >
                {fp.split('/').pop()}
              </a>
              <a href={`/api/file?path=${encodeURIComponent(fp)}&dl=1`} title={t('herunterladen')}>
                ⬇
              </a>
            </span>
          ))}
        </div>
      )
    case 'note':
      return <div className={s.note}>{note(block.note)}</div>
    case 'error':
      return (
        <div className={s.err}>
          {trServer(block.message.startsWith('⚠') ? block.message : `⚠ ${block.message}`)}
        </div>
      )
  }
}

function BotMessage({ item }: { item: BotItem }) {
  const { t } = useTranslation()
  const text = () => (item.markdown ?? speakableText(item.blocks)).trim()
  return (
    <Frame user={false} say={{ id: item.id, text }}>
      <div className={s.bubble}>
        {item.markdown != null ? (
          <Markdown text={item.markdown} />
        ) : (
          <div>
            {item.blocks.map((b, i) => (
              <BlockView key={i} block={b} />
            ))}
            {item.thinking && (
              <div className={s.thinking}>
                {t('Denke nach')}
                <span className={s.dot} />
                <span className={s.dot} />
                <span className={s.dot} />
              </div>
            )}
          </div>
        )}
      </div>
    </Frame>
  )
}

function SysBox({ sys }: { sys: SysBody }) {
  const { t } = useTranslation()
  let body: ReactNode
  if (sys.type === 'help')
    body = (
      <>
        <b>{t('⌨ Befehle')}</b>
        <br />
        <code>/new</code> — {t('neue Session')}
        <br />
        <code>/clear</code> — {t('Ansicht leeren')}
        <br />
        <code>/model [name]</code> —{' '}
        {t('Modell wechseln (Claude, GPT, Gemini, DeepSeek, Ollama …)')}
        <br />
        <code>/llm</code> — {t('KI-Anbieter einrichten (API-Keys, Ollama-URL)')}
        <br />
        <code>/mode [auto|plan|bypassPermissions|default]</code> — {t('Modus wechseln')}
        <br />
        <code>/folder [name]</code> — {t('Arbeitsordner wechseln')}
        <br />
        <code>/skills</code> — {t('Skills-Ansicht')}
        <br />
        <code>/login</code> — {t('bei Claude anmelden (wenn der Token abgelaufen ist)')}
        <br />
        <code>/help</code> — {t('diese Liste')}
        <br />
        <br />
        <span style={{ opacity: 0.7 }}>
          {t(
            'Hinweis: Claudes eingebaute Slash-Befehle funktionieren im Headless-Modus nicht — das hier sind eigene App-Befehle.',
          )}
        </span>
      </>
    )
  else
    body = (
      <>
        {t(sys.note.key, sys.note.params)}
        {sys.code?.length ? (
          <>
            {' '}
            {sys.code.map((c, i) => (
              <span key={c}>
                {i > 0 && ', '}
                <code>{c}</code>
              </span>
            ))}
          </>
        ) : null}
      </>
    )
  return (
    <div className={`${s.msg} ${s.bot}`}>
      <div className={s.helpbox}>{body}</div>
    </div>
  )
}

export function ChatItemView({ item, busy }: { item: ChatItem; busy: boolean }) {
  const note = useNote()
  switch (item.kind) {
    case 'user':
      return <UserMessage item={item} busy={busy} />
    case 'bot':
      return <BotMessage item={item} />
    case 'note':
      return <div className={`${s.note} ${item.center ? s.center : ''}`}>{note(item.note)}</div>
    case 'sys':
      return <SysBox sys={item.sys} />
  }
}
