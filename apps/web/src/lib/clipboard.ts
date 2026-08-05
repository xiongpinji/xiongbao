/**
 * 稳健的剪贴板复制工具
 * navigator.clipboard 仅在安全上下文（https / localhost）可用，
 * 在 http 或 iframe 沙箱中会抛异常，这里自动降级到 execCommand 兜底。
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }
}
