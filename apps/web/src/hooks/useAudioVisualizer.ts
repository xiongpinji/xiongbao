/**
 * 音频可视化 Hook（零依赖）。
 *
 * 功能：
 * - useAudioVisualizer：Web Audio API 频谱分析
 * - 实时频率数据（Uint8Array）
 * - 音量/峰值检测
 * - 支持麦克风/音频元素输入
 *
 * 用法：
 *   const { data, volume, start, stop, isActive } = useAudioVisualizer({ fftSize: 256 });
 *   start(); // 开始监听麦克风
 *   // data: Uint8Array 用于 canvas 绘制
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseAudioVisualizerOptions {
  /** FFT 大小（默认 256） */
  fftSize?: number;
  /** 平滑系数 0-1（默认 0.8） */
  smoothing?: number;
  /** 是否自动开始（默认 false） */
  autoStart?: boolean;
}

interface UseAudioVisualizerReturn {
  /** 频率数据（Uint8Array） */
  data: Uint8Array;
  /** 当前音量 0-1 */
  volume: number;
  /** 峰值 0-1 */
  peak: number;
  /** 是否活跃 */
  isActive: boolean;
  /** 是否支持 */
  isSupported: boolean;
  /** 开始（请求麦克风） */
  start: () => Promise<void>;
  /** 停止 */
  stop: () => void;
  /** 错误 */
  error: string | null;
}

export function useAudioVisualizer(
  options: UseAudioVisualizerOptions = {},
): UseAudioVisualizerReturn {
  const { fftSize = 256, smoothing = 0.8, autoStart = false } = options;

  const [isActive, setIsActive] = useState(false);
  const [volume, setVolume] = useState(0);
  const [peak, setPeak] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<Uint8Array>(new Uint8Array(fftSize / 2));

  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number>(0);
  const peakRef = useRef(0);

  const isSupported = typeof window !== "undefined" && "AudioContext" in window;

  const tick = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;

    const buffer = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(buffer);
    setData(buffer);

    // 计算音量（RMS）
    let sum = 0;
    for (let i = 0; i < buffer.length; i++) {
      sum += buffer[i] * buffer[i];
    }
    const rms = Math.sqrt(sum / buffer.length) / 255;
    setVolume(rms);

    if (rms > peakRef.current) {
      peakRef.current = rms;
      setPeak(rms);
    }

    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const start = useCallback(async () => {
    if (!isSupported) {
      setError("浏览器不支持 Web Audio API");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const ctx = new AudioContext();
      audioCtxRef.current = ctx;

      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = fftSize;
      analyser.smoothingTimeConstant = smoothing;
      source.connect(analyser);
      analyserRef.current = analyser;

      setIsActive(true);
      setError(null);
      peakRef.current = 0;
      rafRef.current = requestAnimationFrame(tick);
    } catch (err: any) {
      setError(err.message || "无法访问麦克风");
    }
  }, [isSupported, fftSize, smoothing, tick]);

  const stop = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    audioCtxRef.current?.close();
    streamRef.current = null;
    audioCtxRef.current = null;
    analyserRef.current = null;
    setIsActive(false);
    setVolume(0);
  }, []);

  useEffect(() => {
    if (autoStart) start();
    return () => {
      cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      audioCtxRef.current?.close();
    };
  }, []);

  return { data, volume, peak, isActive, isSupported, start, stop, error };
}

export default useAudioVisualizer;
