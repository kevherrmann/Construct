import type { FolderNode } from '@/api/chat'
import { folderLabel, indexTree, isContainer, recentFolders, rememberFolder } from './folders'

const n = (path: string, project: boolean, children: FolderNode[] = []): FolderNode => ({
  path,
  name: path.split('/').pop()!,
  project,
  children,
})
const tree = n('/h/Projekte', false, [
  n('/h/Projekte/Construct', true),
  n('/h/Projekte/Firma', false, [
    n('/h/Projekte/Firma/webseite', true),
    n('/h/Projekte/Firma/kunden', false, [n('/h/Projekte/Firma/kunden/fahrsignal', true)]),
  ]),
])

it('Index kennt Eltern und relativen Pfad', () => {
  const idx = indexTree(tree)
  const e = idx.get('/h/Projekte/Firma/kunden/fahrsignal')!
  expect(e.rel).toBe('Firma/kunden/fahrsignal')
  expect(e.parent?.name).toBe('kunden')
  expect(idx.get('/h/Projekte')!.parent).toBeNull()
})

it('Kurzname zeigt verschachtelte Ordner mit Elternteil', () => {
  const idx = indexTree(tree)
  expect(folderLabel('/h/Projekte', idx)).toBe('Projekte')
  expect(folderLabel('/h/Projekte/Construct', idx)).toBe('Construct')
  expect(folderLabel('/h/Projekte/Firma/kunden/fahrsignal', idx)).toBe('kunden › fahrsignal')
  expect(folderLabel('/woanders/x', idx)).toBe('x')
})

it('nur Sammelordner sind aufklappbar', () => {
  expect(isContainer(tree.children[0]!)).toBe(false)
  expect(isContainer(tree.children[1]!)).toBe(true)
})

it('zuletzt benutzte: neueste zuerst, ohne Doppelte, begrenzt', () => {
  for (const p of ['a', 'b', 'c', 'a', 'd', 'e', 'f']) rememberFolder(p)
  expect(recentFolders()).toEqual(['f', 'e', 'd', 'a', 'c'])
})
