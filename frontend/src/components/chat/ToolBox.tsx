import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Block } from '@/lib/chat/types'
import { toolSummary } from '@/lib/chat/tools'
import s from './ToolBox.module.css'

type ToolBlock = Extract<Block, { t: 'tool' }>

// Edit/Write als rot/grün-Diff statt rohem JSON — Kontrolle auf einen Blick.
function Diff({ name, input }: { name: string; input: Record<string, unknown> }) {
  const { t } = useTranslation()
  const cap = (v: unknown) => {
    const str = String(v ?? '')
    return str.slice(0, 4000) + (str.length > 4000 ? `\n… ${t('(gekürzt)')}` : '')
  }
  const file = <div className={s.file}>📄 {String(input.file_path ?? '')}</div>
  if (name === 'Write' && typeof input.content === 'string')
    return (
      <>
        {file}
        <div className={`${s.df} ${s.add}`}>{cap(input.content)}</div>
      </>
    )
  const edits =
    name === 'MultiEdit' && Array.isArray(input.edits)
      ? (input.edits as Record<string, unknown>[])
      : 'old_string' in input || 'new_string' in input
        ? [input]
        : null
  if (!edits) return null
  return (
    <>
      {file}
      {edits.map((e, i) => (
        <div key={i}>
          {e.old_string ? <div className={`${s.df} ${s.del}`}>{cap(e.old_string)}</div> : null}
          <div className={`${s.df} ${s.add}`}>{cap(e.new_string)}</div>
        </div>
      ))}
    </>
  )
}

export function ToolBox({ block }: { block: ToolBlock }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const input = block.input
  const obj = input && typeof input === 'object' ? (input as Record<string, unknown>) : null
  const diff = obj ? <Diff name={block.name} input={obj} /> : null
  const hasDiff =
    !!obj &&
    ((block.name === 'Write' && typeof obj.content === 'string') ||
      (block.name === 'MultiEdit' && Array.isArray(obj.edits)) ||
      'old_string' in obj ||
      'new_string' in obj)
  const err = block.result?.isError
  return (
    <div className={`${s.box} ${err ? s.error : ''}`}>
      <button type="button" className={s.head} onClick={() => setOpen((o) => !o)}>
        <span className={s.ic}>⚙</span>
        <span className={s.name}>{block.name}</span>
        <span className={s.sum}>{toolSummary(input)}</span>
        <span className={s.st}>{block.result ? (err ? '✗' : '✓') : '⏳'}</span>
        <span className={s.tg}>{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className={s.body}>
          <div className={s.lbl}>{t('EINGABE')}</div>
          <div className={s.in}>
            {hasDiff ? diff : obj ? JSON.stringify(obj, null, 2) : String(input ?? '')}
          </div>
          {block.result && (
            <>
              <div className={`${s.lbl} ${s.olbl}`}>{t('ERGEBNIS')}</div>
              <div className={s.out}>
                {block.result.content.trim() ? block.result.content : t('(kein Ergebnis)')}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
