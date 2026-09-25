import { render } from '@testing-library/react'
import { rich } from './rich'

const html = (s: string) => render(<p>{rich(s)}</p>).container.firstElementChild!.innerHTML

it('macht b, code und br zu Elementen', () => {
  expect(html('a <b>fett</b> und <code>x.json</code><br>z')).toBe(
    'a <b>fett</b> und <code>x.json</code><br>z',
  )
})

it('verschachtelt', () => {
  expect(html('<b>a <code>b</code></b>')).toBe('<b>a <code>b</code></b>')
})

it('lässt anderes HTML als Text stehen', () => {
  expect(html('<img src=x onerror=alert(1)> <i>k</i>')).toBe(
    '&lt;img src=x onerror=alert(1)&gt; &lt;i&gt;k&lt;/i&gt;',
  )
})

it('verträgt kaputte Auszeichnung', () => {
  expect(html('a </b> <b>offen')).toBe('a &lt;/b&gt; <b>offen</b>')
})
