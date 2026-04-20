export function absoluteUrl(url: string): string {
  if (!url) return "";
  try {
    return new URL(url, window.location.origin).toString();
  } catch (_e) {
    return url;
  }
}

export function shareAbsoluteUrl(url: string, publicBaseUrl = ""): string {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  const base = (publicBaseUrl || "").trim() || window.location.origin;
  try {
    return new URL(url, base).toString();
  } catch (_e) {
    return url;
  }
}

export function buildMediaDirectUrl(
  category: string,
  filename: string,
  readonlyToken = "",
): string {
  const cat = encodeURIComponent(category || "default");
  const name = encodeURIComponent(filename || "");
  const token = readonlyToken ? `?token=${encodeURIComponent(readonlyToken)}` : "";
  return `/files/${cat}/${name}${token}`;
}

export function buildThumbUrl(
  category: string,
  filename: string,
  readonlyToken = "",
  size = 480,
): string {
  const cat = encodeURIComponent(category || "default");
  const name = encodeURIComponent(filename || "");
  const token = readonlyToken ? `?token=${encodeURIComponent(readonlyToken)}` : "";
  const sep = token ? "&" : "?";
  return `/thumb/${cat}/${name}${token}${sep}size=${size}`;
}
