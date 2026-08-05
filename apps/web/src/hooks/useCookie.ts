/**
 * Cookie 管理 Hook（零依赖）。
 *
 * 功能：
 * - useCookie：读写/删除 Cookie
 * - 响应式更新
 * - 支持过期/路径/安全选项
 *
 * 用法：
 *   const [theme, setTheme, removeTheme] = useCookie("theme", "dark");
 *   setTheme("light", { days: 365 });
 */

import { useCallback, useState } from "react";

interface CookieOptions {
  /** 有效天数 */
  days?: number;
  /** 路径（默认 /） */
  path?: string;
  /** 域 */
  domain?: string;
  /** Secure */
  secure?: boolean;
  /** SameSite */
  sameSite?: "Strict" | "Lax" | "None";
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? decodeURIComponent(match[2]) : null;
}

function setCookieRaw(name: string, value: string, options: CookieOptions = {}): void {
  if (typeof document === "undefined") return;

  const { days, path = "/", domain, secure, sameSite = "Lax" } = options;
  let cookie = `${name}=${encodeURIComponent(value)}; path=${path}; SameSite=${sameSite}`;

  if (days) {
    const expires = new Date(Date.now() + days * 864e5).toUTCString();
    cookie += `; expires=${expires}`;
  }
  if (domain) cookie += `; domain=${domain}`;
  if (secure) cookie += "; secure";

  document.cookie = cookie;
}

function removeCookieRaw(name: string, options: CookieOptions = {}): void {
  setCookieRaw(name, "", { ...options, days: -1 });
}

export function useCookie(
  name: string,
  defaultValue: string = "",
): [string, (value: string, options?: CookieOptions) => void, () => void] {
  const [value, setValue] = useState<string>(() => getCookie(name) ?? defaultValue);

  const set = useCallback(
    (newValue: string, options?: CookieOptions) => {
      setCookieRaw(name, newValue, options);
      setValue(newValue);
    },
    [name],
  );

  const remove = useCallback(() => {
    removeCookieRaw(name);
    setValue(defaultValue);
  }, [name, defaultValue]);

  return [value, set, remove];
}

/** 获取所有 Cookie */
export function getAllCookies(): Record<string, string> {
  if (typeof document === "undefined") return {};
  const result: Record<string, string> = {};
  document.cookie.split(";").forEach((pair) => {
    const [key, val] = pair.trim().split("=");
    if (key) result[key] = decodeURIComponent(val || "");
  });
  return result;
}

export default useCookie;
