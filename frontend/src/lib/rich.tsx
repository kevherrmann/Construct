import { Fragment, createElement, type ReactNode } from 'react'

// Übersetzte Absätze mit etwas Auszeichnung (<b>, <code>, <br>) — wie in der
// alten Oberfläche, deren Wörterbuch ganze Absätze als HTML kannte. Statt
// dangerouslySetInnerHTML werden NUR diese drei Tags zu React-Elementen; alles
// andere bleibt Text. So kann auch ein eingesetzter Name (etwa des Assistenten)
// kein HTML einschleusen.
const TAG = /<(\/?)(b|code|br)\s*\/?>/g

type Node = { tag: string; children: ReactNode[] }

export function rich(text: string): ReactNode {
  const root: Node = { tag: '', children: [] }
  const stack: Node[] = [root]
  let last = 0
  let key = 0
  const top = () => stack[stack.length - 1]!
  for (const m of text.matchAll(TAG)) {
    if (m.index > last) top().children.push(text.slice(last, m.index))
    last = m.index + m[0].length
    const [, close, tag] = m as unknown as [string, string, string]
    if (tag === 'br') top().children.push(<br key={key++} />)
    else if (!close) stack.push({ tag, children: [] })
    else if (stack.length > 1 && top().tag === tag) {
      const n = stack.pop()!
      top().children.push(createElement(n.tag, { key: key++ }, ...n.children))
    } else top().children.push(m[0]) // unpassendes Schließ-Tag: als Text lassen
  }
  if (last < text.length) top().children.push(text.slice(last))
  // Nicht geschlossene Tags: Inhalt trotzdem zeigen.
  while (stack.length > 1) {
    const n = stack.pop()!
    top().children.push(createElement(n.tag, { key: key++ }, ...n.children))
  }
  return <Fragment>{root.children}</Fragment>
}
