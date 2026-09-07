import { createI18n } from 'vue-i18n';
import de from './de.json';

// Exported so component specs build an i18n instance that matches production
// (vue-i18n 11 warns when `d(date, 'short')` is called and the composer has no
// matching datetime format).
export const datetimeFormats = {
  de: {
    short: {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    },
    time: { hour: '2-digit', minute: '2-digit', second: '2-digit' },
  },
} as const;

// German is the launch locale. i18n is wired now so no user-facing string is
// hard-coded in components (MASTER_PROMPT §6 "i18n vorbereiten").
export const i18n = createI18n({
  legacy: false,
  locale: 'de',
  fallbackLocale: 'de',
  messages: { de },
  datetimeFormats,
});
