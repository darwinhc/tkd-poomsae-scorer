import { afterEach, describe, expect, it } from 'vitest';
import { detectDeviceLocale, getLanguage, resolveLanguage, setLocale, t, translate } from '@/i18n';
import { errorMessage, LocalizedError } from '@/i18n/LocalizedError';
import { en } from '@/i18n/locales/en';
import { es } from '@/i18n/locales/es';

const placeholdersOf = (text: string) => (text.match(/\{\w+\}/g) ?? []).sort();

describe('i18n locales', () => {
  it('defines exactly the same keys in en and es', () => {
    expect(Object.keys(es).sort()).toEqual(Object.keys(en).sort());
  });

  it('uses the same placeholders in en and es for every key', () => {
    for (const key of Object.keys(en) as (keyof typeof en)[]) {
      expect(placeholdersOf(es[key]), key).toEqual(placeholdersOf(en[key]));
    }
  });

  it('has no empty translations', () => {
    for (const [key, value] of [...Object.entries(en), ...Object.entries(es)]) {
      expect(value.trim().length, key).toBeGreaterThan(0);
    }
  });
});

describe('i18n language resolution', () => {
  const initialLanguage = getLanguage();

  afterEach(() => {
    setLocale(initialLanguage);
  });

  it('maps Spanish locales to es and everything else to en', () => {
    expect(resolveLanguage('es')).toBe('es');
    expect(resolveLanguage('es-MX')).toBe('es');
    expect(resolveLanguage('es_419')).toBe('es');
    expect(resolveLanguage('ES-es')).toBe('es');
    expect(resolveLanguage('en-US')).toBe('en');
    expect(resolveLanguage('fr-FR')).toBe('en');
    expect(resolveLanguage('')).toBe('en');
    expect(resolveLanguage(undefined)).toBe('en');
    expect(resolveLanguage(null)).toBe('en');
  });

  it('reads the device locale through Intl', () => {
    expect(detectDeviceLocale()).toBe(Intl.DateTimeFormat().resolvedOptions().locale);
  });

  it('falls back to English for unknown locales', () => {
    expect(setLocale('de-DE')).toBe('en');
    expect(t('common.cancel')).toBe(en['common.cancel']);
    expect(setLocale('xx')).toBe('en');
    expect(t('summary.title')).toBe('SUMMARY');
  });

  it('translates into Spanish for Spanish locales', () => {
    setLocale('es-AR');
    expect(t('common.cancel')).toBe(es['common.cancel']);
  });

  it('interpolates placeholders and leaves unknown ones untouched', () => {
    expect(translate('en', 'settings.retention', { min: 2 })).toBe('Retention (min 2)');
    expect(translate('en', 'common.versus', { left: 'Competitor A' })).toBe('Competitor A vs {right}');
  });
});

describe('LocalizedError', () => {
  const initialLanguage = getLanguage();

  afterEach(() => {
    setLocale(initialLanguage);
  });

  it('keeps an English message and localizes it for display', () => {
    const error = new LocalizedError('errors.loadStationsFailed', { status: 500 }, { status: 500 });
    expect(error.message).toBe('Could not load stations (500)');
    expect(error.status).toBe(500);

    setLocale('es');
    expect(errorMessage(error)).toBe(translate('es', 'errors.loadStationsFailed', { status: 500 }));
    expect(errorMessage(new Error('plain'))).toBe('plain');
    expect(errorMessage('raw')).toBe('raw');
  });
});
