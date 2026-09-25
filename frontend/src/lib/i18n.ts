import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from '@/i18n/en.json'
import type { Lang } from './bootstrap'

// Deutsch ist die Quellsprache: Schlüssel SIND die deutschen Texte. Für "de"
// gibt es darum kein Wörterbuch — i18next liefert den Schlüssel zurück. Fehlt
// eine englische Übersetzung, erscheint ebenfalls der deutsche Text.
// Platzhalter wie in der alten Oberfläche: {name}.
export function initI18n(lang: Lang) {
  void i18n.use(initReactI18next).init({
    lng: lang,
    fallbackLng: false,
    resources: { en: { translation: en } },
    keySeparator: false,
    nsSeparator: false,
    returnEmptyString: false,
    interpolation: { escapeValue: false, prefix: '{', suffix: '}' },
  })
  document.documentElement.lang = lang
  return i18n
}

/** Gebietsschema für Datum/Zahl, passend zur Oberflächensprache. */
export const locale = (lang: Lang) => (lang === 'de' ? 'de-DE' : 'en-GB')
