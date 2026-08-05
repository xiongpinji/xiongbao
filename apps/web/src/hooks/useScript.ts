/**
 * 异步脚本加载 Hook（零依赖）。
 *
 * 功能：
 * - useScript：动态加载外部 JS 脚本
 * - 加载状态追踪
 * - 去重（同一 URL 只加载一次）
 * - 支持 async/defer
 *
 * 用法：
 *   const status = useScript("https://cdn.example.com/lib.js");
 *   if (status === "ready") { /* 使用 lib *\/ }
 */

import { useEffect, useState } from "react";

type ScriptStatus = "idle" | "loading" | "ready" | "error";

// 全局脚本状态缓存
const scriptCache = new Map<string, ScriptStatus>();
const scriptListeners = new Map<string, Set<(status: ScriptStatus) => void>>();

function notifyListeners(src: string, status: ScriptStatus) {
  scriptCache.set(src, status);
  scriptListeners.get(src)?.forEach((fn) => fn(status));
}

export function useScript(
  src: string | null,
  options: { async?: boolean; defer?: boolean; removeOnUnmount?: boolean } = {},
): ScriptStatus {
  const { async: isAsync = true, defer = false, removeOnUnmount = false } = options;

  const [status, setStatus] = useState<ScriptStatus>(() => {
    if (!src) return "idle";
    return scriptCache.get(src) || "idle";
  });

  useEffect(() => {
    if (!src) {
      setStatus("idle");
      return;
    }

    // 已加载/加载中
    const cached = scriptCache.get(src);
    if (cached === "ready" || cached === "error") {
      setStatus(cached);
      return;
    }

    // 注册监听
    if (!scriptListeners.has(src)) {
      scriptListeners.set(src, new Set());
    }
    const listener = (s: ScriptStatus) => setStatus(s);
    scriptListeners.get(src)!.add(listener);

    // 如果已在加载中，只监听
    if (cached === "loading") {
      setStatus("loading");
      return () => {
        scriptListeners.get(src)?.delete(listener);
      };
    }

    // 开始加载
    setStatus("loading");
    notifyListeners(src, "loading");

    const script = document.createElement("script");
    script.src = src;
    script.async = isAsync;
    script.defer = defer;

    const onLoad = () => notifyListeners(src, "ready");
    const onError = () => notifyListeners(src, "error");

    script.addEventListener("load", onLoad);
    script.addEventListener("error", onError);
    document.body.appendChild(script);

    return () => {
      scriptListeners.get(src)?.delete(listener);
      script.removeEventListener("load", onLoad);
      script.removeEventListener("error", onError);
      if (removeOnUnmount) {
        document.body.removeChild(script);
        scriptCache.delete(src);
      }
    };
  }, [src, isAsync, defer, removeOnUnmount]);

  return status;
}

export default useScript;
