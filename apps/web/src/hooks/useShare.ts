/**
 * Web Share Hook（零依赖）。
 *
 * 功能：
 * - useShare：调用原生分享面板
 * - 支持文本/URL/文件分享
 * - 能力检测 + 降级复制
 *
 * 用法：
 *   const { share, isSupported } = useShare();
 *   <button onClick={() => share({ title: "标题", url: location.href })}>分享</button>
 */

import { useCallback, useState } from "react";

interface ShareData {
  title?: string;
  text?: string;
  url?: string;
  files?: File[];
}

interface UseShareReturn {
  /** 是否支持 Web Share API */
  isSupported: boolean;
  /** 是否支持文件分享 */
  canShareFiles: boolean;
  /** 触发分享 */
  share: (data: ShareData) => Promise<boolean>;
  /** 是否正在分享 */
  isSharing: boolean;
}

export function useShare(): UseShareReturn {
  const [isSharing, setIsSharing] = useState(false);

  const isSupported =
    typeof navigator !== "undefined" && !!navigator.share;

  const canShareFiles =
    typeof navigator !== "undefined" &&
    !!navigator.canShare &&
    navigator.canShare({ files: [new File([], "test.txt")] });

  const share = useCallback(
    async (data: ShareData): Promise<boolean> => {
      if (!isSupported) {
        // 降级：复制到剪贴板
        try {
          const text = [data.title, data.text, data.url]
            .filter(Boolean)
            .join("\n");
          await navigator.clipboard.writeText(text);
          return true;
        } catch {
          return false;
        }
      }

      setIsSharing(true);
      try {
        const sharePayload: any = {};
        if (data.title) sharePayload.title = data.title;
        if (data.text) sharePayload.text = data.text;
        if (data.url) sharePayload.url = data.url;
        if (data.files && canShareFiles) sharePayload.files = data.files;

        await navigator.share(sharePayload);
        return true;
      } catch (err: any) {
        // 用户取消不算失败
        if (err?.name === "AbortError") return false;
        return false;
      } finally {
        setIsSharing(false);
      }
    },
    [isSupported, canShareFiles],
  );

  return { isSupported, canShareFiles, share, isSharing };
}

export default useShare;
