import { useChat } from './chat'

// Alt+Enter / ⏳: die Nachricht wartet, bis der Lauf vorbei ist, statt in ihn hinein.
it('hinten anstellen geht in die Warteschlange, nicht in den laufenden Lauf', async () => {
  const fetchSpy = vi.fn()
  vi.stubGlobal('fetch', fetchSpy)
  const key = useChat.getState().activeKey!
  useChat.setState((s) => ({
    convs: { ...s.convs, [key]: { ...s.convs[key]!, busy: true, runId: 'r1' } },
  }))
  await useChat.getState().send('erst danach', { hinten: true })
  expect(useChat.getState().convs[key]!.queue).toEqual([
    { text: 'erst danach', images: [], urls: [] },
  ])
  expect(fetchSpy).not.toHaveBeenCalled()
  vi.unstubAllGlobals()
})
