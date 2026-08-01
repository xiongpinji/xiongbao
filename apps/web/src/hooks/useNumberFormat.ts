/**
 * 数字格式化 Hook（零依赖）。
 *
 * 功能：
 * - useNumberFormat：数字格式化（千分位/货币/百分比/单位）
 * - 响应式 locale
 * - 输入时实时格式化
 *
 * 用法：
 *   const { format, formatCurrency, formatPercent } = useNumberFormat("zh-CN");
 *   format(1234567.89) // "1,234,567.89"
 */

import { useCallback, useMemo } from "react";

interface UseNumberFormatOptions {
  /** 默认小数位 */
  minFractionDigits?: number;
  maxFractionDigits?: number;
  /** 是否使用千分位 */
  useGrouping?: boolean;
  /** 大数缩写阈值 */
  compactThreshold?: number;
}

interface UseNumberFormatReturn {
  /** 通用格式化 */
  format: (value: number, opts?: Intl.NumberFormatOptions) => string;
  /** 货币格式化 */
  formatCurrency: (value: number, currency?: string) => string;
  /** 百分比格式化 */
  formatPercent: (value: number, decimals?: number) => string;
  /** 大数缩写（1.2万/3.4亿） */
  formatCompact: (value: number) => string;
  /** 文件大小格式化 */
  formatBytes: (bytes: number, decimals?: number) => string;
  /** 解析格式化字符串为数字 */
  parse: (str: string) => number;
}

export function useNumberFormat(
  locale: string = "zh-CN",
  options: UseNumberFormatOptions = {},
): UseNumberFormatReturn {
  const {
    minFractionDigits = 0,
    maxFractionDigits = 2,
    useGrouping = true,
    compactThreshold = 10000,
  } = options;

  const baseFormatter = useMemo(
    () =>
      new Intl.NumberFormat(locale, {
        minimumFractionDigits: minFractionDigits,
        maximumFractionDigits: maxFractionDigits,
        useGrouping,
      }),
    [locale, minFractionDigits, maxFractionDigits, useGrouping],
  );

  const format = useCallback(
    (value: number, opts?: Intl.NumberFormatOptions) => {
      if (opts) {
        return new Intl.NumberFormat(locale, opts).format(value);
      }
      return baseFormatter.format(value);
    },
    [baseFormatter, locale],
  );

  const formatCurrency = useCallback(
    (value: number, currency: string = "CNY") => {
      return new Intl.NumberFormat(locale, {
        style: "currency",
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(value);
    },
    [locale],
  );

  const formatPercent = useCallback(
    (value: number, decimals: number = 1) => {
      return new Intl.NumberFormat(locale, {
        style: "percent",
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(value);
    },
    [locale],
  );

  const formatCompact = useCallback(
    (value: number) => {
      const abs = Math.abs(value);
      if (abs < compactThreshold) return baseFormatter.format(value);

      const sign = value < 0 ? "-" : "";
      if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(1)}亿`;
      if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(1)}万`;
      return baseFormatter.format(value);
    },
    [baseFormatter, compactThreshold],
  );

  const formatBytes = useCallback(
    (bytes: number, decimals: number = 2) => {
      if (bytes === 0) return "0 B";
      const k = 1024;
      const sizes = ["B", "KB", "MB", "GB", "TB", "PB"];
      const i = Math.floor(Math.log(Math.abs(bytes)) / Math.log(k));
      const idx = Math.min(i, sizes.length - 1);
      return `${(bytes / Math.pow(k, idx)).toFixed(decimals)} ${sizes[idx]}`;
    },
    [],
  );

  const parse = useCallback(
    (str: string) => {
      // 移除千分位和空格
      const cleaned = str.replace(/[,\s]/g, "");
      const num = parseFloat(cleaned);
      return isNaN(num) ? 0 : num;
    },
    [],
  );

  return { format, formatCurrency, formatPercent, formatCompact, formatBytes, parse };
}

export default useNumberFormat;
