/**
 * 无障碍公告 Hook（ARIA Live Region）。
 *
 * 功能：
 * - useAriaLive：屏幕阅读器动态公告
 * - 支持 polite / assertive 优先级
 * - 自动清理 + 去重
 *
 * 用法：
 *   const { announce, AriaLiveRegion } = useAriaLive();
 *   announce("保存成功");           // polite
 *   announce("错误！", "assertive"); // assertive
 *   // 在 JSX 中: <AriaLiveRegion />
 */

import { useCallback, useRef, useState } from "react";

type AriaPriority = "polite" | "assertive";

interface UseAriaLiveReturn {
  /** 发布公告 */
  announce: (message: string, priority?: AriaPriority) => void;
  /** 清除公告 */
  clear: () => void;
  /** 渲染 Live Region（放在 JSX 中） */
  AriaLiveRegion: () => JSX.Element;
}

export function useAriaLive(): UseAriaLiveReturn {
  const [politeMsg, setPoliteMsg] = useState("");
  const [assertiveMsg, setAssertiveMsg] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastMsgRef = useRef("");

  const announce = useCallback(
    (message: string, priority: AriaPriority = "polite") => {
      // 去重：相同消息添加空格强制重新播报
      const finalMsg =
        message === lastMsgRef.current ? `${message} ` : message;
      lastMsgRef.current = message;

      if (priority === "assertive") {
        setAssertiveMsg(finalMsg);
      } else {
        setPoliteMsg(finalMsg);
      }

      // 5 秒后清空（避免重复播报）
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        setPoliteMsg("");
        setAssertiveMsg("");
      }, 5000);
    },
    [],
  );

  const clear = useCallback(() => {
    setPoliteMsg("");
    setAssertiveMsg("");
    lastMsgRef.current = "";
  }, []);

  const AriaLiveRegion = useCallback(
    (): JSX.Element => (
      <>
        {/* Polite：不打断当前播报 */}
        <div
          aria-live="polite"
          aria-atomic="true"
          className="sr-only absolute h-px w-px overflow-hidden whitespace-nowrap"
          style={{
            clip: "rect(0, 0, 0, 0)",
            clipPath: "inset(50%)",
          }}
        >
          {politeMsg}
        </div>

        {/* Assertive：立即打断播报 */}
        <div
          aria-live="assertive"
          aria-atomic="true"
          className="sr-only absolute h-px w-px overflow-hidden whitespace-nowrap"
          style={{
            clip: "rect(0, 0, 0, 0)",
            clipPath: "inset(50%)",
          }}
        >
          {assertiveMsg}
        </div>
      </>
    ),
    [politeMsg, assertiveMsg],
  );

  return { announce, clear, AriaLiveRegion };
}

export default useAriaLive;
