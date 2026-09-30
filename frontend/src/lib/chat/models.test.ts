import { modelInfo, extModels, successor } from './models'
import type { Provider } from '@/api/providers'

// Nur die Felder, die die Modell-Logik liest.
const prov = [
  {
    id: 'ollama',
    label: 'Ollama (lokal)',
    configured: true,
    models: ['gemma3:12b'],
    tools: { 'gemma3:12b': true },
    error: '',
  },
  { id: 'openai', label: 'ChatGPT', configured: false, models: ['gpt-4o'], tools: {}, error: '' },
] as Provider[]

describe('modelInfo', () => {
  it('findet Einträge der Liste direkt', () => {
    expect(modelInfo('claude-opus-5-5')?.l).toBe('Opus 5.5')
    expect(modelInfo('')?.l).toBe('Standard')
  })
  it('führt Aliase, Datumsstempel und Kontext-Zusätze auf den Listeneintrag zurück', () => {
    expect(modelInfo('opus')?.l).toBe('Opus 5.5')
    expect(modelInfo('claude-haiku-4-5-20251001')?.l).toBe('Haiku 4.5')
    expect(modelInfo('claude-opus-5-5[1m]')?.l).toBe('Opus 5.5')
  })
  it('zeigt ausgemusterte Claude-Modelle mit roher ID statt "Standard"', () => {
    expect(modelInfo('claude-opus-4-8')).toMatchObject({ l: 'opus-4-8' })
    // Präfix gilt nur in eine Richtung: Sonnet 5 ist nicht Sonnet 5.5
    expect(modelInfo('claude-sonnet-5')).toMatchObject({ l: 'sonnet-5' })
    // Alias, dessen Ziel nicht mehr in der Liste steht (CLI 2.1.283: sonnet → 5)
    expect(modelInfo('sonnet')).toMatchObject({ l: 'sonnet-5' })
  })
  it('stellt gespeicherte ausgemusterte Modelle auf den Nachfolger um', () => {
    expect(successor('claude-opus-5')).toBe('claude-opus-5-5')
    expect(successor('claude-sonnet-5')).toBe('claude-sonnet-5-5')
    expect(successor('claude-opus-4-8')).toBe('claude-opus-4-8')
    expect(successor('')).toBe('')
  })
  it('kennt externe Modelle, auch wenn die Anbieterliste fehlt', () => {
    expect(modelInfo('ollama:gemma3:12b', prov)).toMatchObject({ l: 'gemma3:12b', prov: 'ollama' })
    expect(modelInfo('deepseek:deepseek-chat')).toMatchObject({
      l: 'deepseek-chat',
      prov: 'deepseek',
    })
  })
  it('liefert nur Modelle konfigurierter Anbieter', () => {
    expect(extModels(prov).map((m) => m.v)).toEqual(['ollama:gemma3:12b'])
  })
})
