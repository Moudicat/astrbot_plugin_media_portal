export function safeGet<T = unknown>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch (_e) {
    return fallback;
  }
}

export function safeSet(key: string, value: unknown): void {
  try {
    if (value === undefined || value === null) {
      localStorage.removeItem(key);
      return;
    }
    localStorage.setItem(key, JSON.stringify(value));
  } catch (_e) {
    // 忽略配额/隐私模式错误
  }
}

export function safeRemove(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch (_e) {
    // ignore
  }
}
