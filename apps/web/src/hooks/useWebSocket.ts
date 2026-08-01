/**
 * WebSocket 客户端 Hook（零依赖）。
 *
 * 功能：
 * - useWebSocket：管理 WebSocket 连接生命周期
 * - 自动重连（指数退避）
 * - 心跳 Ping/Pong
 * - 消息队列（连接前缓存）
 *
 * 用法：
 *   const { send, lastMessage, status } = useWebSocket("wss://api.example.com/ws", {
 *     onMessage: (data) => handleEvent(data),
 *   });
 */

import { useCallback, useEffect, useRef, useState } from "react";

type WSStatus = "connecting" | "open" | "closing" | "closed";

interface UseWebSocketOptions {
  /** 收到消息回调 */
  onMessage?: (data: any) => void;
  /** 连接打开回调 */
  onOpen?: () => void;
  /** 连接关闭回调 */
  onClose?: (code: number, reason: string) => void;
  /** 错误回调 */
  onError?: (error: Event) => void;
  /** 是否自动连接（默认 true） */
  autoConnect?: boolean;
  /** 最大重连次数（默认 5） */
  maxReconnect?: number;
  /** 心跳间隔 ms（默认 30000，0=禁用） */
  heartbeatInterval?: number;
  /** 协议 */
  protocols?: string | string[];
}

interface UseWebSocketReturn {
  /** 发送消息（自动 JSON 序列化） */
  send: (data: any) => void;
  /** 最近一条消息 */
  lastMessage: any;
  /** 连接状态 */
  status: WSStatus;
  /** 手动连接 */
  connect: () => void;
  /** 手动断开 */
  disconnect: () => void;
  /** 重连次数 */
  reconnectCount: number;
}

export function useWebSocket(
  url: string,
  options: UseWebSocketOptions = {},
): UseWebSocketReturn {
  const {
    onMessage,
    onOpen,
    onClose,
    onError,
    autoConnect = true,
    maxReconnect = 5,
    heartbeatInterval = 30000,
    protocols,
  } = options;

  const [status, setStatus] = useState<WSStatus>("closed");
  const [lastMessage, setLastMessage] = useState<any>(null);
  const [reconnectCount, setReconnectCount] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const queueRef = useRef<string[]>([]);
  const reconnectRef = useRef(0);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const clearHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus("connecting");
    const ws = new WebSocket(url, protocols);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("open");
      reconnectRef.current = 0;
      setReconnectCount(0);
      optionsRef.current.onOpen?.();

      // 发送队列中的消息
      while (queueRef.current.length > 0) {
        ws.send(queueRef.current.shift()!);
      }

      // 心跳
      if (heartbeatInterval > 0) {
        clearHeartbeat();
        heartbeatRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, heartbeatInterval);
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // 忽略 pong
        if (data?.type === "pong") return;
        setLastMessage(data);
        optionsRef.current.onMessage?.(data);
      } catch {
        setLastMessage(event.data);
        optionsRef.current.onMessage?.(event.data);
      }
    };

    ws.onclose = (event) => {
      setStatus("closed");
      clearHeartbeat();
      optionsRef.current.onClose?.(event.code, event.reason);

      // 自动重连
      if (reconnectRef.current < maxReconnect) {
        reconnectRef.current += 1;
        setReconnectCount(reconnectRef.current);
        const delay = Math.min(1000 * 2 ** reconnectRef.current, 30000);
        setTimeout(() => connect(), delay);
      }
    };

    ws.onerror = (event) => {
      optionsRef.current.onError?.(event);
    };
  }, [url, protocols, maxReconnect, heartbeatInterval, clearHeartbeat]);

  const disconnect = useCallback(() => {
    reconnectRef.current = maxReconnect; // 阻止重连
    clearHeartbeat();
    if (wsRef.current) {
      setStatus("closing");
      wsRef.current.close(1000, "Client disconnect");
    }
  }, [maxReconnect, clearHeartbeat]);

  const send = useCallback((data: any) => {
    const msg = typeof data === "string" ? data : JSON.stringify(data);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(msg);
    } else {
      queueRef.current.push(msg);
    }
  }, []);

  useEffect(() => {
    if (autoConnect) connect();
    return () => {
      reconnectRef.current = maxReconnect;
      clearHeartbeat();
      wsRef.current?.close();
    };
  }, [autoConnect, connect, maxReconnect, clearHeartbeat]);

  return { send, lastMessage, status, connect, disconnect, reconnectCount };
}

export default useWebSocket;
