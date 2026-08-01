/**
 * 拖放区域 Hook（零依赖）。
 *
 * 功能：
 * - useDropZone：文件拖放上传区域
 * - 拖入高亮状态
 * - 文件类型/大小过滤
 * - 支持点击选择
 *
 * 用法：
 *   const { dropRef, isOver, files, openPicker } = useDropZone({
 *     accept: ["image/*"],
 *     maxSize: 5 * 1024 * 1024,
 *     onDrop: (files) => upload(files),
 *   });
 *   <div ref={dropRef} className={isOver ? "highlight" : ""}>拖放文件</div>
 */

import { useCallback, useRef, useState } from "react";

interface UseDropZoneOptions {
  /** 允许的 MIME 类型（如 ["image/*", "application/pdf"]） */
  accept?: string[];
  /** 最大文件大小（bytes） */
  maxSize?: number;
  /** 最大文件数（默认 10） */
  maxFiles?: number;
  /** 多文件（默认 true） */
  multiple?: boolean;
  /** 拖放回调 */
  onDrop?: (files: File[]) => void;
  /** 拒绝回调 */
  onReject?: (reason: string, file?: File) => void;
  /** 是否禁用 */
  disabled?: boolean;
}

interface UseDropZoneReturn {
  /** 绑定到容器 */
  dropRef: React.RefObject<HTMLDivElement | null>;
  /** 文件拖入悬停中 */
  isOver: boolean;
  /** 是否拖拽中（含子元素） */
  isDragging: boolean;
  /** 最近一次接收的文件 */
  files: File[];
  /** 打开文件选择器 */
  openPicker: () => void;
  /** 隐藏 input ref */
  inputRef: React.RefObject<HTMLInputElement | null>;
}

export function useDropZone(options: UseDropZoneOptions = {}): UseDropZoneReturn {
  const {
    accept,
    maxSize,
    maxFiles = 10,
    multiple = true,
    onDrop,
    onReject,
    disabled = false,
  } = options;

  const [isOver, setIsOver] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);

  const dropRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dragCounter = useRef(0);

  const validateFile = useCallback(
    (file: File): string | null => {
      if (maxSize && file.size > maxSize) {
        return `文件 ${file.name} 超过大小限制 (${(maxSize / 1024 / 1024).toFixed(1)}MB)`;
      }
      if (accept && accept.length > 0) {
        const matched = accept.some((pattern) => {
          if (pattern.endsWith("/*")) {
            return file.type.startsWith(pattern.replace("/*", "/"));
          }
          return file.type === pattern;
        });
        if (!matched) {
          return `文件 ${file.name} 类型不支持`;
        }
      }
      return null;
    },
    [accept, maxSize],
  );

  const processFiles = useCallback(
    (fileList: FileList | File[]) => {
      if (disabled) return;

      const incoming = Array.from(fileList);
      const valid: File[] = [];

      for (const file of incoming.slice(0, maxFiles)) {
        const error = validateFile(file);
        if (error) {
          onReject?.(error, file);
        } else {
          valid.push(file);
        }
      }

      if (valid.length > 0) {
        setFiles(valid);
        onDrop?.(valid);
      }
    },
    [disabled, maxFiles, validateFile, onDrop, onReject],
  );

  const handleDragEnter = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (disabled) return;
      dragCounter.current++;
      setIsDragging(true);
      setIsOver(true);
    },
    [disabled],
  );

  const handleDragLeave = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      dragCounter.current--;
      if (dragCounter.current <= 0) {
        dragCounter.current = 0;
        setIsOver(false);
        setIsDragging(false);
      }
    },
    [],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      dragCounter.current = 0;
      setIsOver(false);
      setIsDragging(false);

      if (disabled) return;
      if (e.dataTransfer.files.length > 0) {
        processFiles(e.dataTransfer.files);
      }
    },
    [disabled, processFiles],
  );

  const openPicker = useCallback(() => {
    if (disabled) return;
    // 动态创建 input
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = multiple;
    if (accept) input.accept = accept.join(",");
    input.onchange = () => {
      if (input.files) processFiles(input.files);
    };
    input.click();
  }, [disabled, multiple, accept, processFiles]);

  // 绑定事件到 ref（通过回调 ref）
  const setDropRef = useCallback(
    (el: HTMLDivElement | null) => {
      // 移除旧事件
      if (dropRef.current) {
        dropRef.current.removeEventListener("dragenter", handleDragEnter as any);
        dropRef.current.removeEventListener("dragleave", handleDragLeave as any);
        dropRef.current.removeEventListener("dragover", handleDragOver as any);
        dropRef.current.removeEventListener("drop", handleDrop as any);
      }
      dropRef.current = el;
      if (el) {
        el.addEventListener("dragenter", handleDragEnter as any);
        el.addEventListener("dragleave", handleDragLeave as any);
        el.addEventListener("dragover", handleDragOver as any);
        el.addEventListener("drop", handleDrop as any);
      }
    },
    [handleDragEnter, handleDragLeave, handleDragOver, handleDrop],
  );

  return {
    dropRef: { current: dropRef.current } as React.RefObject<HTMLDivElement | null>,
    isOver,
    isDragging,
    files,
    openPicker,
    inputRef,
  };
}

export default useDropZone;
