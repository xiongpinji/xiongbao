/**
 * 文本选择 Hook（零依赖）。
 *
 * 功能：
 * - useTextSelection：监听用户文本选择
 * - 获取选中文本/范围/坐标
 * - 选中变化回调
 *
 * 用法：
 *   const { text, rect, isEmpty } = useTextSelection();
 *   {!isEmpty && <Tooltip x={rect.x} y={rect.y}>{text}</Tooltip>}
 */

import { useCallback, useEffect, useState } from "react";

interface SelectionRect {
  x: number;
  y: number;
  width: number;
  height: number;
  top: number;
  left: number;
  bottom: number;
  right: number;
}

interface UseTextSelectionReturn {
  /** 选中的文本 */
  text: string;
  /** 选区包围盒 */
  rect: SelectionRect | null;
  /** 是否为空 */
  isEmpty: boolean;
  /** 选区对象 */
  selection: Selection | null;
  /** 清除选择 */
  clear: () => void;
}

const EMPTY_RECT: SelectionRect = { x: 0, y: 0, width: 0, height: 0, top: 0, left: 0, bottom: 0, right: 0 };

export function useTextSelection(
  onSelection?: (text: string) => void,
): UseTextSelectionReturn {
  const [text, setText] = useState("");
  const [rect, setRect] = useState<SelectionRect | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);

  const handleSelectionChange = useCallback(() => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) {
      setText("");
      setRect(null);
      setSelection(null);
      return;
    }

    const selectedText = sel.toString().trim();
    setText(selectedText);
    setSelection(sel);

    if (selectedText && sel.rangeCount > 0) {
      const range = sel.getRangeAt(0);
      const domRect = range.getBoundingClientRect();
      setRect({
        x: domRect.x,
        y: domRect.y,
        width: domRect.width,
        height: domRect.height,
        top: domRect.top,
        left: domRect.left,
        bottom: domRect.bottom,
        right: domRect.right,
      });
      onSelection?.(selectedText);
    } else {
      setRect(null);
    }
  }, [onSelection]);

  useEffect(() => {
    document.addEventListener("selectionchange", handleSelectionChange);
    return () => document.removeEventListener("selectionchange", handleSelectionChange);
  }, [handleSelectionChange]);

  const clear = useCallback(() => {
    window.getSelection()?.removeAllRanges();
    setText("");
    setRect(null);
    setSelection(null);
  }, []);

  return { text, rect, isEmpty: !text, selection, clear };
}

export default useTextSelection;
