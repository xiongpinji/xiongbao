/**
 * 全站统一的数字格式化工具（纯函数，可在任意上下文使用）。
 *
 * 纯函数设计，适用于组件外（store/工具函数）及无需 hook 生命周期的场景。
 */

/** 整数千分位：1234567 → "1,234,567"。空值/NaN 返回 "0"。 */
export function formatInt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "0";
  return Math.round(n).toLocaleString("zh-CN");
}

/**
 * 固定小数位 + 千分位：formatDecimal(1234.5, 2) → "1,234.50"。
 * 默认 2 位小数。
 */
export function formatDecimal(n: number | null | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return "0";
  return n.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/**
 * 费用/成本显示：小额（< 0.01）保留 6 位有效精度，常规保留 4 位，均带千分位。
 * 避免极小值显示为 "0.0000" 丢失信息。
 */
export function formatCost(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "0";
  const abs = Math.abs(n);
  const digits = abs > 0 && abs < 0.01 ? 6 : 4;
  return n.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** 文件大小：自动选择 B/KB/MB/GB 单位。 */
export function formatBytes(bytes: number, decimals = 1): string {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(Math.abs(bytes)) / Math.log(k)), sizes.length - 1);
  return `${(bytes / Math.pow(k, i)).toFixed(decimals)} ${sizes[i]}`;
}
