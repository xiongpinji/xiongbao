/**
 * 语音识别 Hook（零依赖）。
 *
 * 功能：
 * - useSpeechRecognition：Web Speech API 语音转文字
 * - 实时中间结果 + 最终结果
 * - 连续/单次模式
 * - 语言配置
 *
 * 用法：
 *   const { transcript, isListening, start, stop } = useSpeechRecognition({ lang: "zh-CN" });
 *   <button onClick={start}>开始录音</button>
 *   <p>{transcript}</p>
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseSpeechRecognitionOptions {
  /** 语言（默认 zh-CN） */
  lang?: string;
  /** 是否连续识别（默认 false） */
  continuous?: boolean;
  /** 是否返回中间结果（默认 true） */
  interimResults?: boolean;
  /** 最终结果回调 */
  onResult?: (text: string) => void;
  /** 错误回调 */
  onError?: (error: string) => void;
}

interface UseSpeechRecognitionReturn {
  /** 当前识别文本（含中间结果） */
  transcript: string;
  /** 最终确认文本 */
  finalTranscript: string;
  /** 是否正在监听 */
  isListening: boolean;
  /** 是否支持 */
  isSupported: boolean;
  /** 开始 */
  start: () => void;
  /** 停止 */
  stop: () => void;
  /** 重置 */
  reset: () => void;
}

export function useSpeechRecognition(
  options: UseSpeechRecognitionOptions = {},
): UseSpeechRecognitionReturn {
  const {
    lang = "zh-CN",
    continuous = false,
    interimResults = true,
    onResult,
    onError,
  } = options;

  const [transcript, setTranscript] = useState("");
  const [finalTranscript, setFinalTranscript] = useState("");
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  const SpeechRecognition =
    typeof window !== "undefined"
      ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      : null;

  const isSupported = !!SpeechRecognition;

  const start = useCallback(() => {
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.lang = lang;
    recognition.continuous = continuous;
    recognition.interimResults = interimResults;

    recognition.onresult = (event: any) => {
      let interim = "";
      let final = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const text = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          final += text;
        } else {
          interim += text;
        }
      }
      if (final) {
        setFinalTranscript((prev) => prev + final);
        onResult?.(final);
      }
      setTranscript(interim || final);
    };

    recognition.onerror = (event: any) => {
      onError?.(event.error || "recognition error");
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  }, [SpeechRecognition, lang, continuous, interimResults, onResult, onError]);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);

  const reset = useCallback(() => {
    setTranscript("");
    setFinalTranscript("");
  }, []);

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
    };
  }, []);

  return {
    transcript,
    finalTranscript,
    isListening,
    isSupported,
    start,
    stop,
    reset,
  };
}

export default useSpeechRecognition;
