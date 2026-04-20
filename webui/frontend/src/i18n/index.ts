import { createI18n } from "vue-i18n";
import zhCN from "./locales/zh-CN.json";

export const SUPPORTED_LOCALES = ["zh-CN", "en-US", "ja-JP"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

const LS_KEY = "media_portal_locale";

export const LOCALE_LABELS: Record<Locale, string> = {
  "zh-CN": "简体中文",
  "en-US": "English",
  "ja-JP": "日本語",
};

function detectLocale(): Locale {
  try {
    const saved = localStorage.getItem(LS_KEY) as Locale | null;
    if (saved && (SUPPORTED_LOCALES as readonly string[]).includes(saved)) return saved;
  } catch (_e) {
    // ignore
  }
  const nav = (typeof navigator !== "undefined" && navigator.language) || "zh-CN";
  if (nav.startsWith("ja")) return "ja-JP";
  if (nav.startsWith("en")) return "en-US";
  return "zh-CN";
}

export const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: "zh-CN",
  messages: { "zh-CN": zhCN as any },
  missingWarn: false,
  fallbackWarn: false,
});

const loadedLocales = new Set<Locale>(["zh-CN"]);

export async function setLocale(locale: Locale): Promise<void> {
  if (!(SUPPORTED_LOCALES as readonly string[]).includes(locale)) return;
  if (!loadedLocales.has(locale)) {
    const messages = await import(`./locales/${locale}.json`);
    i18n.global.setLocaleMessage(locale, messages.default || messages);
    loadedLocales.add(locale);
  }
  (i18n.global.locale as unknown as { value: Locale }).value = locale;
  try {
    document.documentElement.setAttribute("lang", locale);
    localStorage.setItem(LS_KEY, locale);
  } catch (_e) {
    // ignore
  }
}

export function currentLocale(): Locale {
  return (i18n.global.locale as unknown as { value: Locale }).value;
}

export function bootstrapLocale(): Promise<void> {
  const target = detectLocale();
  if (target === "zh-CN") {
    document.documentElement.setAttribute("lang", "zh-CN");
    return Promise.resolve();
  }
  return setLocale(target);
}
