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
  expect(trServer('Die lokale Stimme antwortet nach 300s nicht.')).toBe(
    'The local voice is not responding after 300 s.',
  )
  expect(trServer('Ollama (lokal)')).toBe('Ollama (local)')
})

it('lokale Stimme: Meldungen mit Werten (Wortlaut wie in tests/test_tts_lokal.py)', () => {
  expect(
    trServer(
      'Zu wenig freier Grafikspeicher für die lokale Stimme: 2.1 GB frei, gebraucht werden etwa 4 GB. Läuft gerade ein Spiel oder ein anderes KI-Modell?',
    ),
  ).toBe(
    'Not enough free graphics memory for the local voice: 2.1 GB free, about 4 GB needed. Is a game or another AI model running?',
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
  expect(trServer('Ollama (lokal)')).toBe('Ollama (lokal)')
  await i18n.changeLanguage('en')
})
