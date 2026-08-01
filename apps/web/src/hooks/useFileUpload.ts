/**
 * 文件上传 Hook（零依赖）。
 *
 * 功能：
 * - useFileUpload：拖放/选择文件上传
 * - 进度跟踪 + 取消
 * - 文件类型/大小验证
 * - 多文件队列
 *
 * 用法：
 *   const { files, addFiles, upload, progress, isUploading } = useFileUpload({
 *     endpoint: "/api/v1/uploads",
 *     maxSize: 10 * 1024 * 1024,
 *     accept: ["image/*", "video/*"],
 *   });
 */

import { useCallback, useRef, useState } from "react";

interface UploadFile {
  id: string;
  file: File;
  status: "pending" | "uploading" | "done" | "error";
  progress: number;
  error?: string;
}

interface UseFileUploadOptions {
  /** 上传端点 */
  endpoint: string;
  /** 最大文件大小（bytes，默认 50MB） */
  maxSize?: number;
  /** 允许的 MIME 类型 */
  accept?: string[];
  /** 最大文件数（默认 10） */
  maxFiles?: number;
  /** 上传完成回调 */
  onComplete?: (file: UploadFile) => void;
  /** 错误回调 */
  onError?: (file: UploadFile, error: string) => void;
}

interface UseFileUploadReturn {
  files: UploadFile[];
  addFiles: (fileList: FileList | File[]) => void;
  removeFile: (id: string) => void;
  uploadAll: () => Promise<void>;
  clear: () => void;
  isUploading: boolean;
  overallProgress: number;
  inputRef: React.RefObject<HTMLInputElement | null>;
}

let idCounter = 0;

export function useFileUpload(options: UseFileUploadOptions): UseFileUploadReturn {
  const {
    endpoint,
    maxSize = 50 * 1024 * 1024,
    accept,
    maxFiles = 10,
    onComplete,
    onError,
  } = options;

  const [files, setFiles] = useState<UploadFile[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const abortControllers = useRef<Map<string, AbortController>>(new Map());

  const validateFile = useCallback(
    (file: File): string | null => {
      if (file.size > maxSize) {
        return `文件过大（${(file.size / 1024 / 1024).toFixed(1)}MB > ${(maxSize / 1024 / 1024).toFixed(0)}MB）`;
      }
      if (accept && accept.length > 0) {
        const matched = accept.some((pattern) => {
          if (pattern.endsWith("/*")) {
            return file.type.startsWith(pattern.replace("/*", "/"));
          }
          return file.type === pattern;
        });
        if (!matched) return `不支持的文件类型: ${file.type}`;
      }
      return null;
    },
    [maxSize, accept],
  );

  const addFiles = useCallback(
    (fileList: FileList | File[]) => {
      const newFiles: UploadFile[] = [];
      const arr = Array.from(fileList);

      for (const file of arr) {
        if (files.length + newFiles.length >= maxFiles) break;
        const error = validateFile(file);
        newFiles.push({
          id: `upload_${++idCounter}`,
          file,
          status: error ? "error" : "pending",
          progress: 0,
          error: error || undefined,
        });
      }

      setFiles((prev) => [...prev, ...newFiles]);
    },
    [files.length, maxFiles, validateFile],
  );

  const removeFile = useCallback((id: string) => {
    const controller = abortControllers.current.get(id);
    controller?.abort();
    abortControllers.current.delete(id);
    setFiles((prev) => prev.filter((f) => f.id !== id));
  }, []);

  const uploadAll = useCallback(async () => {
    setIsUploading(true);

    const pending = files.filter((f) => f.status === "pending");

    for (const uploadFile of pending) {
      const controller = new AbortController();
      abortControllers.current.set(uploadFile.id, controller);

      setFiles((prev) =>
        prev.map((f) =>
          f.id === uploadFile.id ? { ...f, status: "uploading" as const } : f,
        ),
      );

      try {
        const formData = new FormData();
        formData.append("file", uploadFile.file);

        const xhr = new XMLHttpRequest();
        await new Promise<void>((resolve, reject) => {
          xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
              const pct = Math.round((e.loaded / e.total) * 100);
              setFiles((prev) =>
                prev.map((f) =>
                  f.id === uploadFile.id ? { ...f, progress: pct } : f,
                ),
              );
            }
          };
          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) resolve();
            else reject(new Error(`HTTP ${xhr.status}`));
          };
          xhr.onerror = () => reject(new Error("Network error"));
          xhr.onabort = () => reject(new Error("Aborted"));
          xhr.open("POST", endpoint);
          xhr.send(formData);
        });

        setFiles((prev) =>
          prev.map((f) =>
            f.id === uploadFile.id
              ? { ...f, status: "done" as const, progress: 100 }
              : f,
          ),
        );
        onComplete?.(uploadFile);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Upload failed";
        setFiles((prev) =>
          prev.map((f) =>
            f.id === uploadFile.id
              ? { ...f, status: "error" as const, error: msg }
              : f,
          ),
        );
        onError?.(uploadFile, msg);
      }
    }

    setIsUploading(false);
  }, [files, endpoint, onComplete, onError]);

  const clear = useCallback(() => {
    abortControllers.current.forEach((c) => c.abort());
    abortControllers.current.clear();
    setFiles([]);
    setIsUploading(false);
  }, []);

  const overallProgress =
    files.length > 0
      ? Math.round(
          files.reduce((sum, f) => sum + f.progress, 0) / files.length,
        )
      : 0;

  return {
    files,
    addFiles,
    removeFile,
    uploadAll,
    clear,
    isUploading,
    overallProgress,
    inputRef,
  };
}

export default useFileUpload;
