/** React hooks over the WS socket (docs/13 §5.2). */

"use client";

import { useEffect, useRef, useState } from "react";

import type { CanonicalEvent, Detection, WSFrame } from "@/lib/api/types";
import { getSocket } from "./socket";

export interface SimLiveState {
  events: CanonicalEvent[];
  detections: Detection[];
  status: string;
  lagMs: number;
}

/** Subscribe to `sim.{id}`; appends events/detections as frames arrive. */
export function useSimulationChannel(simId: string | null): SimLiveState {
  const [state, setState] = useState<SimLiveState>({
    events: [],
    detections: [],
    status: "connecting",
    lagMs: 0,
  });
  const eventsRef = useRef<CanonicalEvent[]>([]);
  const detectionsRef = useRef<Detection[]>([]);

  useEffect(() => {
    if (!simId) return;
    eventsRef.current = [];
    detectionsRef.current = [];
    const sock = getSocket();
    const channel = `sim.${simId}`;
    sock.subscribe(channel);

    const off = sock.onFrame((frame: WSFrame) => {
      if (frame.kind === "event.upsert") {
        eventsRef.current = [...eventsRef.current, frame.event];
        setState((s) => ({ ...s, events: eventsRef.current }));
      } else if (frame.kind === "event.batch") {
        eventsRef.current = [...eventsRef.current, ...frame.events];
        setState((s) => ({ ...s, events: eventsRef.current }));
      } else if (frame.kind === "detection.created") {
        detectionsRef.current = [...detectionsRef.current, frame.detection];
        setState((s) => ({ ...s, detections: detectionsRef.current }));
      } else if (frame.kind === "sim.status") {
        setState((s) => ({ ...s, status: frame.status }));
      } else if (frame.kind === "sim.lag") {
        setState((s) => ({ ...s, lagMs: frame.lag_ms }));
      } else if (frame.kind === "action.executed") {
        setState((s) => ({ ...s, status: s.status }));
      }
    });

    return () => {
      off();
      sock.unsubscribe(channel);
    };
  }, [simId]);

  return state;
}
