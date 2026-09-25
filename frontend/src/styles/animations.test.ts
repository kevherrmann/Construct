// CSS Modules benennen Animationsnamen um. Die gemeinsamen Keyframes aus
// global.css müssen darum per global(name) angesprochen werden — sonst steht
// z. B. der Cursor beim Streamen still, ohne dass es eine Fehlermeldung gibt.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const SRC = join(__dirname, '..')
const modules = (dir: string): string[] =>
  readdirSync(dir).flatMap((f) => {
    const p = join(dir, f)
    if (statSync(p).isDirectory()) return modules(p)
    return f.endsWith('.module.css') ? [p] : []
  })

it('gemeinsame Keyframes werden in Modulen global angesprochen', () => {
  const bad: string[] = []
  for (const f of modules(SRC)) {
    const css = readFileSync(f, 'utf8')
    for (const m of css.matchAll(/animation(?:-name)?:\s*(blink|pulse|fade)\b/g))
      bad.push(`${f.slice(SRC.length + 1)}: ${m[0]}`)
  }
  expect(bad).toEqual([])
})
