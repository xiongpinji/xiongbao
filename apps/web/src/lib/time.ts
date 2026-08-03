/**
 * 全站统一的时间格式化工具（单一来源，避免各组件各自实现导致格式不一致）。
 *
 * 约定：自动兼容秒级与毫秒级 Unix 时间戳——数值 < 1e11 视为秒级，否则视为毫秒级。
 * （当前毫秒时间戳约 1.7e12，秒级约 1.7e9，阈值 1e11 可安全区分两者。）
 */

/** 将秒级或毫秒级时间戳归一为毫秒。 */
function toMillis(ts: number): number {
  return ts < 1e11 ? ts * 1000 : ts;
}

/** 相对时间：刚刚 / N 分钟前 / N 小时前 / N 天前。空值返回空串。 */
export function timeAgo(ts: number): string {
  if (!ts) return "";
  const diff = (Date.now() - toMillis(ts)) / 1000;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}

/** 时刻：HH:mm（24 小时制）。空值返回空串。 */
export function formatTime(ts: number): string {
  if (!ts) return "";
  return new Date(toMillis(ts)).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * 完整日期时间：zh-CN 本地化、24 小时制。
 * 支持数字时间戳（秒/毫秒）与 ISO 字符串；无法解析时原样返回字符串。
 */
export function formatDateTime(ts: number | string): string {
  if (!ts) return "";
  const date = typeof ts === "string" ? new Date(ts) : new Date(toMillis(ts));
  return Number.isNaN(date.getTime()) ? String(ts) : date.toLocaleString("zh-CN", { hour12: false });
}
