// Die Werkzeugliste der Akte muss die des Servers sein (KNOWN_TOOLS): fehlt dort
// eines, meldet der Server beim Speichern „unbekanntes Werkzeug“; fehlt es hier,
// kann man es nicht vergeben.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { WERKZEUGE } from './team'

it('Werkzeuge wie KNOWN_TOOLS im Server', () => {
  const py = readFileSync(join(__dirname, '../../../server/team/agents.py'), 'utf8')
  const block = /KNOWN_TOOLS = \(([\s\S]*?)\)/.exec(py)![1]!
  const server = [...block.matchAll(/"([A-Za-z]+)"/g)].map((m) => m[1])
  expect(WERKZEUGE.map((x) => x.w).sort()).toEqual(server.sort())
})
