/**
 * DOM 变更监听 Hook（零依赖）。
 *
 * 功能：
 * - useMutationObserver：监听 DOM 树变更
 * - 支持 childList / attributes / characterData
 * - 变更回调 + 记录
 *
 * 用法：
 *   const ref = useRef<HTMLDivElement>(null);
 *   const mutations = useMutationObserver(ref, { childList: true, subtree: true });
 */

import { useEffect, useRef, useState } from "react";

interface UseMutationObserverOptions {
  /** 监听子节点变化 */
  childList?: boolean;
  /** 监听属性变化 */
  attributes?: boolean;
  /** 监听文本变化 */
  characterData?: boolean;
  /** 包含后代 */
  subtree?: boolean;
  /** 记录旧值 */
  attributeOldValue?: boolean;
  /** 监听特定属性 */
  attributeFilter?: string[];
  /** 是否启用（默认 true） */
  enabled?: boolean;
}

interface MutationRecord_Summary {
  type: string;
  target: string;
  attributeName?: string | null;
  addedNodes: number;
  removedNodes: number;
  timestamp: number;
}

export function useMutationObserver(
  targetRef: React.RefObject<Element | null>,
  options: UseMutationObserverOptions = {},
): MutationRecord_Summary[] {
  const {
    childList = true,
    attributes = false,
    characterData = false,
    subtree = false,
    attributeOldValue = false,
    attributeFilter,
    enabled = true,
  } = options;

  const [mutations, setMutations] = useState<MutationRecord_Summary[]>([]);
  const observerRef = useRef<MutationObserver | null>(null);

  useEffect(() => {
    const element = targetRef.current;
    if (!element || !enabled) return;

    const observer = new MutationObserver((records) => {
      const summaries = records.map((record) => ({
        type: record.type,
        target: record.target.nodeName.toLowerCase(),
        attributeName: record.attributeName,
        addedNodes: record.addedNodes.length,
        removedNodes: record.removedNodes.length,
        timestamp: Date.now(),
      }));
      setMutations((prev) => [...prev.slice(-99), ...summaries]);
    });

    const config: MutationObserverInit = {
      childList,
      attributes,
      characterData,
      subtree,
      attributeOldValue,
    };
    if (attributeFilter) config.attributeFilter = attributeFilter;

    observer.observe(element, config);
    observerRef.current = observer;

    return () => {
      observer.disconnect();
      observerRef.current = null;
    };
  }, [
    targetRef,
    enabled,
    childList,
    attributes,
    characterData,
    subtree,
    attributeOldValue,
    attributeFilter,
  ]);

  return mutations;
}

export default useMutationObserver;
