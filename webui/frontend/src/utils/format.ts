export function formatSize(bytes: number | string | null | undefined): string {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / 1048576).toFixed(1)} MB`;
  return `${(size / 1073741824).toFixed(2)} GB`;
}

export function formatTimestamp(raw: number | string | null | undefined): string {
  if (raw === undefined || raw === null || raw === "") return "";
  const num = Number(raw);
  if (!Number.isFinite(num) || num <= 0) return String(raw);
  const ms = num > 1e12 ? num : num * 1000;
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return String(raw);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

export function formatDateShort(raw: number | string | null | undefined): string {
  if (raw === undefined || raw === null || raw === "") return "";
  const num = Number(raw);
  if (!Number.isFinite(num) || num <= 0) return "";
  const ms = num > 1e12 ? num : num * 1000;
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  if (d.getFullYear() === now.getFullYear()) {
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * 列表/卡片副信息里使用的「较详细」时间：
 *   - 同年：MM-DD HH:mm
 *   - 跨年：YY-MM-DD HH:mm
 */
export function formatDateTimeShort(raw: number | string | null | undefined): string {
  if (raw === undefined || raw === null || raw === "") return "";
  const num = Number(raw);
  if (!Number.isFinite(num) || num <= 0) return "";
  const ms = num > 1e12 ? num : num * 1000;
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (d.getFullYear() === now.getFullYear()) {
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`;
  }
  const yy = String(d.getFullYear()).slice(-2);
  return `${yy}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`;
}

export function formatDuration(raw: number | string | null | undefined): string {
  const num = Number(raw);
  if (!Number.isFinite(num) || num <= 0) return "";
  const total = Math.round(num);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  if (hours > 0) {
    return `${hours}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${minutes}:${pad(seconds)}`;
}
