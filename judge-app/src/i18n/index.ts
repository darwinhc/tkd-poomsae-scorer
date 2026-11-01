import { en, type TranslationKey } from './locales/en';
import { es } from './locales/es';

export type { TranslationKey } from './locales/en';
export type Language = 'en' | 'es';
export type TranslationParams = Record<string, string | number>;

export const DEFAULT_LANGUAGE: Language = 'en';

const dictionaries: Record<Language, Partial<Record<TranslationKey, string>>> = { en, es };

/** Maps a BCP 47 locale tag (e.g. "es-MX", "en_US") to a supported UI language. */
export function resolveLanguage(locale: string | null | undefined): Language {
  if (typeof locale === 'string' && /^es([-_]|$)/i.test(locale.trim())) {
    return 'es';
  }
  return DEFAULT_LANGUAGE;
}

/** Reads the device locale through the Intl API (available in Hermes and Node). */
export function detectDeviceLocale(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().locale;
  } catch {
    return undefined;
  }
}

let currentLanguage: Language = resolveLanguage(detectDeviceLocale());

export function getLanguage(): Language {
  return currentLanguage;
}

/** Overrides the UI language from a locale tag. Unknown locales fall back to English. */
export function setLocale(locale: string | null | undefined): Language {
  currentLanguage = resolveLanguage(locale);
  return currentLanguage;
}

export function translate(language: Language, key: TranslationKey, params?: TranslationParams): string {
  const template = dictionaries[language]?.[key] ?? en[key] ?? key;
  return interpolate(template, params);
}

/** Translates `key` into the current UI language, filling `{name}` placeholders from `params`. */
export function t(key: TranslationKey, params?: TranslationParams): string {
  return translate(currentLanguage, key, params);
}

function interpolate(template: string, params?: TranslationParams): string {
  if (!params) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : placeholder
  );
}
