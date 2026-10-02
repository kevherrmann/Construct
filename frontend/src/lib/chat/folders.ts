// Ordnerbaum für die Ordner-Auswahl im Chat: Index, Kurznamen, zuletzt benutzte.
import type { FolderNode } from '@/api/chat'
import { getItem, setItem } from '@/lib/storage'

const RECENT_KEY = 'mxrecentfolders'
const RECENT_MAX = 5

export function recentFolders(): string[] {
  try {
    const v = JSON.parse(getItem(RECENT_KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : []
  } catch {
    return []
  }
}

export function rememberFolder(path: string) {
  const next = [path, ...recentFolders().filter((p) => p !== path)].slice(0, RECENT_MAX)
  setItem(RECENT_KEY, JSON.stringify(next))
}

export interface FolderEntry {
  node: FolderNode
  parent: FolderNode | null
  rel: string
}

/** Pfad → Knoten + Elternteil + Pfad relativ zum Workspace. */
export function indexTree(root: FolderNode): Map<string, FolderEntry> {
  const map = new Map<string, FolderEntry>()
  const walk = (n: FolderNode, parent: FolderNode | null, rel: string) => {
    map.set(n.path, { node: n, parent, rel })
    for (const c of n.children) walk(c, n, rel ? `${rel}/${c.name}` : c.name)
  }
  walk(root, null, '')
  return map
}

/** Kurzname für die Leiste: "kunden › fahrsignal" statt nur "fahrsignal". */
export function folderLabel(path: string, index: Map<string, FolderEntry> | null): string {
  const rel = index?.get(path)?.rel
  if (rel == null) return path.split('/').filter(Boolean).pop() || path
  if (!rel) return index!.get(path)!.node.name
  return rel.split('/').slice(-2).join(' › ')
}

/** Sammelordner (z.B. "kunden") — kein Projekt, hat aber Unterordner. */
export const isContainer = (n: FolderNode) => !n.project && n.children.length > 0
