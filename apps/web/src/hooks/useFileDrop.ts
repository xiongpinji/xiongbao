/**
 * 拖放文件上传 Hook（零依赖）。
 *
 * 功能：
 * - useFileDrop：拖拽区域文件接收
 * - 支持文件类型/大小过滤
 * - 拖拽状态（dragover / drop / reject）
 * - 多文件 + 进度追踪
 *
 * 用法：
 *   const { getDropProps, isDragging, files, errors } = useFileDrop({
 *     accept: ["image/*", ".pdf"],
 *     maxSize: 10 * 1024 * 1024, // 10MB
 *     multiple: true,
 *     onDrop: (files) => upload(files),
 *   });
 *   <div {...getDropProps()}>拖拽文件到此处</div>
 */

import { useCallback, useRef, useState } from "react";

interface UseFileDropOptions {
  /** 接受的文件类型（MIME 或扩展名） */
  accept?: string[];
  /** 最大文件大小（bytes） */
  maxSize?: number;
  /** 最大文件数量 */
  maxFiles?: number;
  /** 是否多选（默认 true） */
  multiple?: boolean;
  /** 是否禁用 */
  disabled?: boolean;
  /** 拖放回调 */
  onDrop?: (files: File[]) => void;
  /** 拒绝回调 */
  onReject?: (reasons: string[]) => void;
}

interface UseFileDropReturn {
  /** 绑定到拖拽区域的 props */
  getDropProps: () => {
    onDragEnter: (e: React.DragEvent) => void;
    onDragOver: (e: React.DragEvent) => void;
    onDragLeave: (e: React.DragEvent) => void;
    onDrop: (e: React.DragEvent) => void;
    onClick: () => void;
  };
  /** 是否正在拖拽悬停 */
  isDragging: boolean;
  /** 已接受的文件 */
  files: File[];
  /** 拒绝原因列表 */
  errors: string[];
  /** 清空文件 */
  clear: () => void;
  /** 隐藏的文件 input ref */
  inputRef: React.RefObject<HTMLInputElement>;
}

export function useFileDrop(options: UseFileDropOptions = {}): UseFileDropReturn {
  const {
    accept = [],
    maxSize = Infinity,
    maxFiles = Infinity,
    multiple = true,
    disabled = false,
    onDrop,
    onReject,
  } = options;

  const [isDragging, setIsDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const dragCounter = useRef(0);

  const validateFile = useCallback(
    (file: File): string | null => {
      // 类型检查
      if (accept.length > 0) {
        const matched = accept.some((pattern) => {
          if (pattern.endsWith("/*")) {
            // image/* → 匹配 image/ 开头
            return file.type.startsWith(pattern.replace("/*", "/"));
          }
          if (pattern.startsWith(".")) {
            // .pdf → 匹配扩展名
            return file.name.toLowerCase().endsWith(pattern.toLowerCase());
          }
          return file.type === pattern;
        });
        if (!matched) {
          return `${file.name}: 不支持的文件类型`;
        }
      }

      // 大小检查
      if (file.size > maxSize) {
        const mb = (maxSize / 1024 / 1024).toFixed(1);
        return `${file.name}: 超过 ${mb}MB 限制`;
      }

      return null;
    },
    [accept, maxSize],
  );

  const processFiles = useCallback(
    (fileList: FileList | File[]) => {
      const incoming = Array.from(fileList);
      const accepted: File[] = [];
      const rejected: string[] = [];

      for (const file of incoming) {
        const error = validateFile(file);
        if (error) {
          rejected.push(error);
        } else {
          accepted.push(file);
        }
      }

      // 数量限制
      const finalFiles = multiple ? accepted : accepted.slice(0, 1);
      if (finalFiles.length > maxFiles) {
        rejected.push(`最多只能上传 ${maxFiles} 个文件`);
        finalFiles.length = maxFiles;
      }

      setFiles(finalFiles);
      setErrors(rejected);

      if (finalFiles.length > 0) onDrop?.(finalFiles);
      if (rejected.length > 0) onReject?.(rejected);
    },
    [validateFile, multiple, maxFiles, onDrop, onReject],
  );

  const handleDragEnter = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (disabled) return;
      dragCounter.current += 1;
      setIsDragging(true);
    },
    [disabled],
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    },
    [],
  );

  const handleDragLeave = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current -= 1;
      if (dragCounter.current <= 0) {
        dragCounter.current = 0;
        setIsDragging(false);
      }
    },
    [],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current = 0;
      setIsDragging(false);
      if (disabled) return;

      if (e.dataTransfer.files.length > 0) {
        processFiles(e.dataTransfer.files);
      }
    },
    [disabled, processFiles],
  );

  const handleClick = useCallback(() => {
    if (disabled) return;
    inputRef.current?.click();
  }, [disabled]);

  const getDropProps = useCallback(
    () => ({
      onDragEnter: handleDragEnter,
      onDragOver: handleDragOver,
      onDragLeave: handleDragLeave,
      onDrop: handleDrop,
      onClick: handleClick,
    }),
    [handleDragEnter, handleDragOver, handleDragLeave, handleDrop, handleClick],
  );

  const clear = useCallback(() => {
    setFiles([]);
    setErrors([]);
  }, []);

  return { getDropProps, isDragging, files, errors, clear, inputRef };
}

export default useFileDrop;
