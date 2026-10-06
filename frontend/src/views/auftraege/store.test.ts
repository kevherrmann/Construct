import { useAuftraegeAnsicht } from './store'
import { useChat } from '@/stores/chat'

// Das Protokoll im Raum zeigt, was du zuletzt gewählt hast.
beforeEach(() => useAuftraegeAnsicht.setState({ auswahl: null, protokoll: null }))

it('einen Auftrag öffnen zeigt ihn im Protokoll', () => {
  useAuftraegeAnsicht.getState().oeffne('a1')
  expect(useAuftraegeAnsicht.getState().protokoll).toBe('a1')
})

it('vormerken wählt aus, ohne das Protokoll umzustellen', () => {
  useAuftraegeAnsicht.getState().vormerken('a2')
  expect(useAuftraegeAnsicht.getState().auswahl).toBe('a2')
  expect(useAuftraegeAnsicht.getState().protokoll).toBeNull()
})

it('eine neue Session stellt das Protokoll zurück auf den Chat', () => {
  useAuftraegeAnsicht.getState().oeffne('a1')
  useChat.getState().newSession()
  expect(useAuftraegeAnsicht.getState().protokoll).toBeNull()
  // Die Auswahl in den Aufträgen bleibt, nur das Protokoll wechselt.
  expect(useAuftraegeAnsicht.getState().auswahl).toBe('a1')
})
