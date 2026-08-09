/**
 * WebSocket layer (docs/13 §5, docs/08 §5).
 * One socket per session; `useSimulationChannel` subscribes to sim channels.
 */

import type { WSFrame } from "@/lib/api/types";
import { api, tokenStore } from "@/lib/api/client";

type FrameListener = (frame: WSFrame) => void;

class SimulationSocket {
  private ws: WebSocket | null = null;
  private listeners = new Set<FrameListener>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private lastSeq = 0;
  private shouldRun = false;

  start(): void {
    this.shouldRun = true;
    this.connect();
  }

  stop(): void {
    this.shouldRun = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }

  private async connect(): Promise<void> {
    if (!tokenStore.access) {
      this.scheduleReconnect(2000);
      return;
    }
    let ticket: string;
    try {
      const t = await api.wsTicket();
      ticket = t.ticket;
    } catch {
      this.scheduleReconnect(3000);
      return;
    }

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const base = (
      process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000"
    ).replace(/^http/, "ws");
    const ws = new WebSocket(`${base}/v1/ws?ticket=${ticket}`);
    this.ws = ws;

    ws.onopen = () => {
      if (this.lastSeq > 0) {
        // resume subscriptions for any active sim (set by hooks)
        for (const sub of activeChannels) {
          ws.send(
            JSON.stringify({
              kind: "subscribe",
              channel: sub,
              cursors: { events: this.lastSeq },
            }),
          );
        }
      }
    };
    ws.onmessage = (ev) => {
      try {
        const frame = JSON.parse(ev.data as string) as WSFrame;
        if (frame.kind === "event.upsert") this.lastSeq = frame.event.sequence;
        for (const l of this.listeners) l(frame);
      } catch {
        /* malformed frame — ignore */
      }
    };
    ws.onclose = () => {
      this.ws = null;
      if (this.shouldRun) this.scheduleReconnect(2500);
    };
    ws.onerror = () => ws.close();
  }

  private scheduleReconnect(delay: number): void {
    if (!this.shouldRun) return;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => void this.connect(), delay);
  }

  onFrame(listener: FrameListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  subscribe(channel: string): void {
    activeChannels.add(channel);
    this.ws?.send(
      JSON.stringify({
        kind: "subscribe",
        channel,
        cursors: { events: this.lastSeq },
      }),
    );
  }

  unsubscribe(channel: string): void {
    activeChannels.delete(channel);
    this.ws?.send(JSON.stringify({ kind: "unsubscribe", channel }));
  }
}

const activeChannels = new Set<string>();
let socket: SimulationSocket | null = null;

export function getSocket(): SimulationSocket {
  if (!socket) {
    socket = new SimulationSocket();
    socket.start();
  }
  return socket;
}

export type { FrameListener };
