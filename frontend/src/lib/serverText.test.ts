import i18n from 'i18next'
import { initI18n } from './i18n'
import { trServer } from './serverText'

beforeAll(() => {
  initI18n('en')
})
afterAll(() => {
  void i18n.changeLanguage('de')
})

it('übersetzt bekannte Texte zeilenweise', () => {
  expect(trServer('API-Key von platform.deepseek.com')).toBe('API key from platform.deepseek.com')
  expect(
    trServer('🦙 Ollama nicht erreichbar — läuft es? (Standard: Port 11434)\n\n[Errno 61] x'),
  ).toBe('🦙 Ollama unreachable — is it running? (default: port 11434)\n\n[Errno 61] x')
})

it('setzt Werte ein und kennt (lokal)', () => {
  expect(
    trServer(
      'PrismML-Bonsai über den llama-server des Bonsai-Demos — startet erst beim ersten Prompt und räumt den VRAM nach 10 Min Leerlauf wieder frei',
    ),
  ).toMatch(/after 10 min of inactivity$/)
  expect(trServer('Bonsai (lokal)')).toBe('Bonsai (local)')
})

it('lokale Stimme: Meldungen mit Werten (Wortlaut wie in tests/test_tts_lokal.py)', () => {
  expect(
    trServer(
      'Zu wenig freier Grafikspeicher für die lokale Stimme: 2.1 GB frei, gebraucht werden etwa 4 GB. Läuft gerade Bonsai, ein Spiel oder ein anderes KI-Modell?',
    ),
  ).toBe(
    'Not enough free graphics memory for the local voice: 2.1 GB free, about 4 GB needed. Is Bonsai, a game or another AI model running?',
  )
  expect(
    trServer(
      'Die lokale Stimme ist noch nicht installiert — ⚙ Einstellungen → Vorlesen → Installieren.',
    ),
  ).toMatch(/^The local voice is not installed yet/)
})

it('lässt Unbekanntes und leere Werte stehen', () => {
  expect(trServer('irgendwas Neues')).toBe('irgendwas Neues')
  expect(trServer(undefined)).toBe('')
})

it('ändert auf Deutsch nichts', async () => {
  await i18n.changeLanguage('de')
  expect(trServer('Bonsai (lokal)')).toBe('Bonsai (lokal)')
  await i18n.changeLanguage('en')
})
