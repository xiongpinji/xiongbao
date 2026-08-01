/**
 * 打字机效果 Hook（零依赖）。
 *
 * 功能：
 * - useTypewriter：逐字显示文本
 * - 支持速度控制 + 光标闪烁
 * - 多段文本循环播放
 * - 暂停/继续/跳过
 *
 * 用法：
 *   const { text, isTyping, skip } = useTypewriter("Hello, World!", { speed: 50 });
 *   <p>{text}<span className="cursor">|</span></p>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseTypewriterOptions {
  /** 每字符间隔（ms，默认 50） */
  speed?: number;
  /** 是否自动开始（默认 true） */
  autoStart?: boolean;
  /** 是否循环（默认 false） */
  loop?: boolean;
  /** 循环间停顿（ms，默认 2000） */
  loopDelay?: number;
  /** 完成回调 */
  onComplete?: () => void;
  /** 是否显示光标（默认 true） */
  showCursor?: boolean;
}

interface UseTypewriterReturn {
  /** 当前显示的文本 */
  text: string;
  /** 是否正在打字 */
  isTyping: boolean;
  /** 是否完成 */
  isComplete: boolean;
  /** 光标是否可见（闪烁用） */
  cursorVisible: boolean;
  /** 跳过动画（直接显示全部） */
  skip: () => void;
  /** 重新开始 */
  restart: () => void;
  /** 暂停 */
  pause: () => void;
  /** 继续 */
  resume: () => void;
}

export function useTypewriter(
  content: string | string[],
  options: UseTypewriterOptions = {},
): UseTypewriterReturn {
  const {
    speed = 50,
    autoStart = true,
    loop = false,
    loopDelay = 2000,
    onComplete,
    showCursor = true,
  } = options;

  const texts = Array.isArray(content) ? content : [content];
  const [text, setText] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [cursorVisible, setCursorVisible] = useState(true);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cursorTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const indexRef = useRef(0); // 当前字符索引
  const textIndexRef = useRef(0); // 当前文本索引
  const pausedRef = useRef(false);

  // 光标闪烁
  useEffect(() => {
    if (!showCursor) return;
    cursorTimerRef.current = setInterval(() => {
      setCursorVisible((v) => !v);
    }, 530);
    return () => {
      if (cursorTimerRef.current) clearInterval(cursorTimerRef.current);
    };
  }, [showCursor]);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const typeNext = useCallback(() => {
    if (pausedRef.current) return;

    const currentText = texts[textIndexRef.current] || "";

    if (indexRef.current < currentText.length) {
      indexRef.current += 1;
      setText(currentText.slice(0, indexRef.current));
      timerRef.current = setTimeout(typeNext, speed);
    } else {
      // 当前文本打完
      if (textIndexRef.current < texts.length - 1) {
        // 还有下一段
        timerRef.current = setTimeout(() => {
          textIndexRef.current += 1;
          indexRef.current = 0;
          setText("");
          typeNext();
        }, loopDelay / 2);
      } else if (loop) {
        // 循环
        timerRef.current = setTimeout(() => {
          textIndexRef.current = 0;
          indexRef.current = 0;
          setText("");
          setIsComplete(false);
          typeNext();
        }, loopDelay);
      } else {
        // 完成
        setIsTyping(false);
        setIsComplete(true);
        onComplete?.();
      }
    }
  }, [texts, speed, loop, loopDelay, onComplete]);

  const start = useCallback(() => {
    clearTimer();
    indexRef.current = 0;
    textIndexRef.current = 0;
    pausedRef.current = false;
    setText("");
    setIsTyping(true);
    setIsComplete(false);
    timerRef.current = setTimeout(typeNext, speed);
  }, [clearTimer, typeNext, speed]);

  const skip = useCallback(() => {
    clearTimer();
    const currentText = texts[textIndexRef.current] || "";
    setText(currentText);
    indexRef.current = currentText.length;
    setIsTyping(false);
    setIsComplete(true);
  }, [clearTimer, texts]);

  const restart = useCallback(() => {
    start();
  }, [start]);

  const pause = useCallback(() => {
    pausedRef.current = true;
    clearTimer();
  }, [clearTimer]);

  const resume = useCallback(() => {
    pausedRef.current = false;
    typeNext();
  }, [typeNext]);

  useEffect(() => {
    if (autoStart) start();
    return clearTimer;
  }, [autoStart, start, clearTimer]);

  return {
    text,
    isTyping,
    isComplete,
    cursorVisible,
    skip,
    restart,
    pause,
    resume,
  };
}

export default useTypewriter;
