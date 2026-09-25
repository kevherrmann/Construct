// Jeder feste Text in t('…') braucht einen englischen Eintrag — sonst sieht
// die englische Oberfläche an dieser Stelle Deutsch. Der Test findet sie.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import en from './en.json'

const SRC = join(__dirname, '..')
const files = (dir: string): string[] =>
  readdirSync(dir).flatMap((f) => {
    const p = join(dir, f)
    if (statSync(p).isDirectory()) return files(p)
    return /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f) ? [p] : []
  })

// t('…') und t("…") mit einfachem String-Literal als erstem Argument; auch über
// Zeilenumbrüche (Prettier bricht lange Aufrufe um).
const CALL = /\bt\(\s*(['"])((?:\\.|(?!\1).)*)\1/g
const LABEL = /\blabel:\s*'((?:\\.|[^'])*)'/g

it('alle Texte sind übersetzt', () => {
  const dict = en as Record<string, string>
  const missing = new Set<string>()
  for (const f of files(SRC)) {
    const code = readFileSync(f, 'utf8')
    for (const m of code.matchAll(CALL)) {
      const key = m[2]!.replace(/\\(['"\\])/g, '$1')
      if (!(key in dict)) missing.add(`${key}   ← ${f.slice(SRC.length + 1)}`)
    }
    if (f.endsWith('registry.tsx'))
      for (const m of code.matchAll(LABEL))
        if (!(m[1]! in dict)) missing.add(`${m[1]}   ← registry`)
  }
  expect([...missing]).toEqual([])
})
