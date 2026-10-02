import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type { FolderNode } from '@/api/chat'
import { indexTree, isContainer, recentFolders, type FolderEntry } from '@/lib/chat/folders'
import s from './FolderNav.module.css'

type Row =
  | { kind: 'head'; label: string }
  | { kind: 'use'; node: FolderNode }
  | { kind: 'folder'; node: FolderNode; hint?: string }

const selectable = (r: Row) => r.kind !== 'head'
const firstRow = (rows: Row[]) => {
  const f = rows.findIndex((r) => r.kind === 'folder')
  return f >= 0 ? f : rows.findIndex(selectable)
}
const SEARCH_MAX = 60

export function FolderNav({
  tree,
  current,
  onPick,
  onClose,
}: {
  tree: FolderNode
  current: string | null
  onPick: (path: string) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const index = useMemo(() => indexTree(tree), [tree])
  // Beim Öffnen dort stehen, wo der aktuelle Ordner liegt.
  const [level, setLevel] = useState<FolderNode>(() => {
    const e = current ? index.get(current) : undefined
    if (!e) return tree
    return isContainer(e.node) ? e.node : (e.parent ?? tree)
  })
  const [q, setQ] = useState('')
  // Markierte Zeile gehört zu genau einer Zeilenliste — neue Liste, neue Markierung.
  const [mark, setMark] = useState<{ rows: Row[] | null; i: number }>({ rows: null, i: 0 })
  const input = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => input.current?.focus(), [])

  const crumbs = useMemo(() => {
    const out: FolderNode[] = []
    for (let n: FolderNode | null = level; n; n = index.get(n.path)?.parent ?? null) out.unshift(n)
    return out
  }, [level, index])

  const rows = useMemo<Row[]>(() => {
    const needle = q.trim().toLowerCase()
    if (needle) {
      const hits: { e: FolderEntry; score: number }[] = []
      for (const e of index.values()) {
        if (!e.rel) continue
        const name = e.node.name.toLowerCase()
        const score = name.startsWith(needle)
          ? 0
          : name.includes(needle)
            ? 1
            : e.rel.toLowerCase().includes(needle)
              ? 2
              : -1
        if (score >= 0) hits.push({ e, score })
      }
      hits.sort((a, b) => a.score - b.score || a.e.rel.localeCompare(b.e.rel))
      return hits.slice(0, SEARCH_MAX).map(({ e }) => ({
        kind: 'folder',
        node: e.node,
        hint: e.rel.split('/').slice(0, -1).join(' › '),
      }))
    }
    const out: Row[] = []
    if (level === tree) {
      const rec = recentFolders()
        .map((p) => index.get(p))
        .filter((e): e is FolderEntry => !!e && !!e.rel)
      if (rec.length) {
        out.push({ kind: 'head', label: t('ZULETZT') })
        for (const e of rec)
          out.push({
            kind: 'folder',
            node: e.node,
            hint: e.rel.split('/').slice(0, -1).join(' › '),
          })
        out.push({ kind: 'head', label: t('ALLE ORDNER') })
      }
    }
    out.push({ kind: 'use', node: level })
    for (const c of level.children) out.push({ kind: 'folder', node: c })
    return out
  }, [q, index, level, tree, t])

  const active = mark.rows === rows ? mark.i : firstRow(rows)
  const setActive = (i: number) => setMark({ rows, i })

  useEffect(() => {
    listRef.current?.querySelector(`[data-row="${active}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [active])

  const enter = (n: FolderNode) => {
    setLevel(n)
    setQ('')
    input.current?.focus()
  }
  const up = () => {
    const p = index.get(level.path)?.parent
    if (p) enter(p)
  }
  const activate = (r: Row | undefined) => {
    if (!r || r.kind === 'head') return
    if (r.kind === 'folder' && isContainer(r.node) && !q) return enter(r.node)
    onPick(r.node.path)
  }
  const move = (d: 1 | -1) => {
    for (let i = active + d; i >= 0 && i < rows.length; i += d)
      if (selectable(rows[i]!)) return setActive(i)
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    const r = rows[active]
    if (e.key === 'ArrowDown') move(1)
    else if (e.key === 'ArrowUp') move(-1)
    else if (e.key === 'Enter') activate(r)
    else if (e.key === 'Escape') onClose()
    else if (e.key === 'ArrowRight' && r?.kind === 'folder' && isContainer(r.node)) enter(r.node)
    else if ((e.key === 'ArrowLeft' || e.key === 'Backspace') && !q && level !== tree) up()
    else return
    e.preventDefault()
  }

  return (
    <div className={s.nav}>
      <div className={s.top}>
        <input
          ref={input}
          className={s.search}
          value={q}
          placeholder={t('Ordner suchen …')}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKey}
          spellCheck={false}
        />
        {!q && (
          <div className={s.crumbs}>
            {level !== tree && (
              <button type="button" className={s.back} title={t('Eine Ebene hoch')} onClick={up}>
                ‹
              </button>
            )}
            {crumbs.map((c, i) => (
              <span key={c.path} className={s.crumbWrap}>
                {i > 0 && <span className={s.sep}>›</span>}
                <button
                  type="button"
                  className={`${s.crumb} ${c === level ? s.here : ''}`}
                  title={c.path}
                  onClick={() => enter(c)}
                >
                  {i === 0 ? '⌂ ' : ''}
                  {c.name}
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
      <div className={s.rows} ref={listRef}>
        {rows.map((r, i) => {
          if (r.kind === 'head')
            return (
              <div key={`h${i}`} className={s.head}>
                {r.label}
              </div>
            )
          const n = r.node
          const container = r.kind === 'folder' && isContainer(n)
          const cls = [
            s.row,
            i === active ? s.active : '',
            n.path === current ? s.sel : '',
            r.kind === 'use' ? s.use : '',
          ].join(' ')
          return (
            <div
              key={`${r.kind}${n.path}${i}`}
              data-row={i}
              className={cls}
              title={n.path}
              onMouseEnter={() => setActive(i)}
              onClick={() => activate(r)}
            >
              {r.kind === 'use' ? (
                <>
                  <span className={s.icon}>✓</span>
                  <span className={s.label}>
                    {t('Diesen Ordner verwenden')} <span className={s.muted}>· {n.name}</span>
                  </span>
                </>
              ) : (
                <>
                  <span className={s.icon}>{container ? '🗂' : '📂'}</span>
                  <span className={s.label}>
                    {n.name}
                    {r.hint && <span className={s.hint}>{r.hint}</span>}
                  </span>
                  {n.path === current && <span className={s.check}>●</span>}
                  {container && (
                    <>
                      <span className={s.count}>{n.children.length}</span>
                      {q ? (
                        <button
                          type="button"
                          className={s.open}
                          title={t('Öffnen')}
                          onClick={(e) => {
                            e.stopPropagation()
                            enter(n)
                          }}
                        >
                          ›
                        </button>
                      ) : (
                        <span className={s.open}>›</span>
                      )}
                    </>
                  )}
                </>
              )}
            </div>
          )
        })}
        {rows.every((r) => r.kind === 'head' || r.kind === 'use') && (
          <div className={s.empty}>{q ? t('Nichts gefunden') : t('Keine Unterordner')}</div>
        )}
      </div>
      <div className={s.foot}>
        ↑↓ {t('wählen')} · ↵ {t('öffnen/übernehmen')} · ← {t('zurück')}
      </div>
    </div>
  )
}
