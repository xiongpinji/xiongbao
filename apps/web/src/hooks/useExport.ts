/**
 * 数据导出 Hook（零依赖）。
 *
 * 功能：
 * - useExport：导出 JSON / CSV / 文本
 * - 自动触发浏览器下载
 * - 支持自定义文件名 + BOM（Excel 兼容）
 *
 * 用法：
 *   const { exportJSON, exportCSV, exportText } = useExport();
 *   exportCSV(data, { filename: "users.csv", headers: ["姓名", "邮箱"] });
 */

import { useCallback } from "react";

interface ExportCSVOptions {
  filename?: string;
  headers?: string[];
  delimiter?: string;
  bom?: boolean;
}

interface UseExportReturn {
  /** 导出 JSON */
  exportJSON: (data: any, filename?: string) => void;
  /** 导出 CSV */
  exportCSV: (data: Record<string, any>[], options?: ExportCSVOptions) => void;
  /** 导出纯文本 */
  exportText: (text: string, filename?: string) => void;
  /** 导出 Blob */
  exportBlob: (blob: Blob, filename: string) => void;
}

/** 触发浏览器下载 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();

  // 清理
  setTimeout(() => {
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, 100);
}

/** 转义 CSV 字段 */
function escapeCSV(value: any, delimiter: string): string {
  const str = value == null ? "" : String(value);
  if (str.includes(delimiter) || str.includes('"') || str.includes("\n")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

export function useExport(): UseExportReturn {
  const exportBlob = useCallback((blob: Blob, filename: string) => {
    downloadBlob(blob, filename);
  }, []);

  const exportJSON = useCallback(
    (data: any, filename: string = "export.json") => {
      const json = JSON.stringify(data, null, 2);
      const blob = new Blob([json], { type: "application/json;charset=utf-8" });
      downloadBlob(blob, filename.endsWith(".json") ? filename : `${filename}.json`);
    },
    [],
  );

  const exportCSV = useCallback(
    (data: Record<string, any>[], options: ExportCSVOptions = {}) => {
      const {
        filename = "export.csv",
        headers,
        delimiter = ",",
        bom = true,
      } = options;

      if (data.length === 0) {
        downloadBlob(new Blob([""], { type: "text/csv" }), filename);
        return;
      }

      // 确定列
      const columns = headers || Object.keys(data[0]);
      const lines: string[] = [];

      // 表头
      lines.push(columns.map((c) => escapeCSV(c, delimiter)).join(delimiter));

      // 数据行
      for (const row of data) {
        const values = columns.map((col) => escapeCSV(row[col], delimiter));
        lines.push(values.join(delimiter));
      }

      const content = lines.join("\r\n");
      // BOM 让 Excel 正确识别 UTF-8
      const prefix = bom ? "\uFEFF" : "";
      const blob = new Blob([prefix + content], {
        type: "text/csv;charset=utf-8",
      });

      downloadBlob(blob, filename.endsWith(".csv") ? filename : `${filename}.csv`);
    },
    [],
  );

  const exportText = useCallback((text: string, filename: string = "export.txt") => {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    downloadBlob(blob, filename);
  }, []);

  return { exportJSON, exportCSV, exportText, exportBlob };
}

export default useExport;
