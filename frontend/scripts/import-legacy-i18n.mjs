// Einmal-Import: übernimmt das Wörterbuch der alten Oberfläche (static/i18n.js)
// als src/i18n/en.json. Schlüssel bleiben die deutschen Texte — Deutsch ist die
// Quellsprache, fehlt eine Übersetzung, erscheint der deutsche Text.
// Aufruf: node scripts/import-legacy-i18n.mjs   (überschreibt nur neue Schlüssel nicht)
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import vm from 'node:vm'

const src = readFileSync(new URL('../../static/i18n.js', import.meta.url), 'utf8')
const grab = (name) => {
  const m = src.match(new RegExp(`var ${name} = (\\{[\\s\\S]*?\\n\\});`))
  if (!m) throw new Error(`${name} nicht gefunden`)
  return vm.runInNewContext(`(${m[1]})`)
}
const EN = grab('EN')
const HTML = grab('HTML')
const target = new URL('../src/i18n/en.json', import.meta.url)
const current = existsSync(target) ? JSON.parse(readFileSync(target, 'utf8')) : {}
// Bestehende (ggf. von Hand verbesserte) Einträge gewinnen.
const out = { ...EN, ...HTML, ...current }
const sorted = Object.fromEntries(Object.entries(out).sort(([a], [b]) => a.localeCompare(b, 'de')))
writeFileSync(target, JSON.stringify(sorted, null, 2) + '\n')
console.log(`${Object.keys(EN).length} Texte + ${Object.keys(HTML).length} Absätze → ${Object.keys(sorted).length} Einträge`)
