import { act, fireEvent, render } from '@testing-library/react'
import { MarkdownBubble } from './Markdown'

it('hängt an jeden Codeblock einen Kopier-Knopf', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.assign(navigator, { clipboard: { writeText } })
  const { container } = render(<MarkdownBubble text={'```\nls -la\n```\n\n```py\nx = 1\n```'} />)
  const btns = container.querySelectorAll('pre button')
  expect(btns).toHaveLength(2)
  await act(async () => {
    fireEvent.click(btns[0]!)
  })
  expect(writeText).toHaveBeenCalledTimes(1)
  expect(btns[0]!.textContent).toBe('✓ Kopiert')
})
