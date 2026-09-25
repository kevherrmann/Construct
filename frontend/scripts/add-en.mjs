// Englische Einträge ergänzen, sortiert einfügen: node scripts/add-en.mjs '{"Deutsch":"English"}'
import { readFileSync, writeFileSync } from 'node:fs'
const f = new URL('../src/i18n/en.json', import.meta.url)
const cur = JSON.parse(readFileSync(f, 'utf8'))
const add = JSON.parse(process.argv[2] ?? '{}')
const out = Object.fromEntries(
  Object.entries({ ...cur, ...add }).sort(([a], [b]) => a.localeCompare(b, 'de')),
)
writeFileSync(f, JSON.stringify(out, null, 2) + '\n')
console.log(`+${Object.keys(add).length} → ${Object.keys(out).length}`)
