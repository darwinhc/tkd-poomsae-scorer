import { t, translate, type TranslationKey, type TranslationParams } from './index';

/**
 * Error whose user-facing text comes from the translation resources.
 * `message` is always English (for logs and tests); UIs should display it with `errorMessage()`.
 */
export class LocalizedError extends Error {
  readonly key: TranslationKey;
  readonly params?: TranslationParams;
  readonly status?: number;
  /** Machine-readable reason sent by the server next to the HTTP status (e.g. `match_closed`). */
  readonly code?: string;

  constructor(
    key: TranslationKey,
    params?: TranslationParams,
    options?: { status?: number; code?: string; cause?: unknown }
  ) {
    super(translate('en', key, params));
    this.name = 'LocalizedError';
    this.key = key;
    this.params = params;
    this.status = options?.status;
    this.code = options?.code;
    if (options?.cause !== undefined) {
      (this as { cause?: unknown }).cause = options.cause;
    }
  }
}

/** Returns the text to show the user for any thrown value, localized when possible. */
export function errorMessage(error: unknown): string {
  if (error instanceof LocalizedError) {
    return t(error.key, error.params);
  }
  if (error && typeof error === 'object' && typeof (error as { message?: unknown }).message === 'string') {
    return (error as { message: string }).message;
  }
  return String(error);
}
