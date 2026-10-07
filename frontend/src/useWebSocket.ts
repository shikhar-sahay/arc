import { useEffect, useRef, useState } from "react";
import { WebSocketMessage } from "./types";

export type WsStatus = "connected" | "reconnecting" | "disconnected";

const MAX_RETRY_DELAY_MS = 15000;
const BASE_RETRY_MS = 2000;

export function useWebSocket() {
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [wsStatus, setWsStatus] = useState<WsStatus>("reconnecting");
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | undefined>(undefined);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    function getRetryDelay(): number {
      const delay = BASE_RETRY_MS * Math.pow(1.5, retryCountRef.current);
      return Math.min(delay, MAX_RETRY_DELAY_MS);
    }

    function connect() {
      if (!mountedRef.current) return;
      // Close any existing socket before opening a new one
      if (wsRef.current && wsRef.current.readyState < WebSocket.CLOSING) {
        wsRef.current.close();
      }

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/ws`;

      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl);
      } catch {
        if (!mountedRef.current) return;
        setWsStatus("disconnected");
        scheduleReconnect();
        return;
      }

      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) {
          ws.close();
          return;
        }
        retryCountRef.current = 0;
        setWsStatus("connected");
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const data = JSON.parse(event.data) as WebSocketMessage;
          setLastMessage(data);
        } catch {
          // Ignore unparseable frames
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setWsStatus("reconnecting");
        scheduleReconnect();
      };

      ws.onerror = () => {
        // onclose will fire after onerror; no extra action needed
        ws.close();
      };
    }

    function scheduleReconnect() {
      if (!mountedRef.current) return;
      retryCountRef.current += 1;
      const delay = getRetryDelay();
      reconnectTimeoutRef.current = window.setTimeout(connect, delay);
    }

    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimeoutRef.current !== undefined) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  return { wsStatus, lastMessage };
}
