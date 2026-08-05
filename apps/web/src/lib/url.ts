/**
 * URL 安全工具 — 防止 javascript: / data: / vbscript: 等协议注入
 */

const SAFE_PROTOCOLS = new Set(["http:", "https:", "blob:"]);

/**
 * 校验 URL 是否为安全的 http(s)/blob 协议。
 * 返回规范化后的 URL；不安全或无效时返回 null。
 */
export function safeUrl(raw: string): string | null {
  try {
    const parsed = new URL(raw, window.location.origin);
    if (!SAFE_PROTOCOLS.has(parsed.protocol)) return null;
    return parsed.href;
  } catch {
    return null;
  }
}

/**
 * 安全地在新标签页打开 URL（noopener + 协议校验）。
 * 不安全时静默忽略。
 */
export function openSafe(url: string): void {
  const href = safeUrl(url);
  if (!href) return;
  window.open(href, "_blank", "noopener,noreferrer");
}
