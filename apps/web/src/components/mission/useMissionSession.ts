/**
 * Mission session data orchestration (docs/14 §2, §8).
 * Authed mode: REST initial load + WS live channel, score polling.
 * Judge mode: token-addressed REST polling only (no WS ticket for anon).
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, authedRequest } from "@/lib/api/client";
import type {
  CanonicalEvent,
  Detection,
  MissionDetail,
  MissionScore,
} from "@/lib/api/types";
import { useSimulationChannel } from "@/lib/ws/useSimulationChannel";

export interface ExecutedAction {
  action_id: string;
  executed_at: number;
}

export interface MissionSession {
  mission: MissionDetail | null;
  simId: string | null;
  starting: boolean;
  notice: string | null;
  shareUrl: string | null;
  status: string;
  events: CanonicalEvent[];
  detections: Detection[];
  score: MissionScore | null;
  lastAction: ExecutedAction | null;
  start: () => Promise<void>;
  execute: (
    detection: Detection,
    actionId: string,
    confirm: boolean,
  ) => Promise<void>;
}

const POLL_MS = 2000;
const MAX_EVENTS = 500;

function dedupe(a: CanonicalEvent[], b: CanonicalEvent[]): CanonicalEvent[] {
  const seen = new Set<string>();
  return [...a, ...b].filter((e) => {
    if (seen.has(e.event_id)) return false;
    seen.add(e.event_id);
    return true;
  });
}

export function useMissionSession(
  missionId: string | null,
  token: string | null = null,
): MissionSession {
  const judge = token !== null;
  const [mission, setMission] = useState<MissionDetail | null>(null);
  const [simId, setSimId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [status, setStatus] = useState("queued");
  const [events, setEvents] = useState<CanonicalEvent[]>([]);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [score, setScore] = useState<MissionScore | null>(null);
  const [lastAction, setLastAction] = useState<ExecutedAction | null>(null);
  const simIdRef = useRef<string | null>(null);
  const tokenRef = useRef<string | null>(token);

  const live = useSimulationChannel(judge ? null : simId);

  // initial load: authed → mission detail; judge → mission + sim via token
  useEffect(() => {
    if (judge && token) {
      void api
        .publicMission(token)
        .then((view) => {
          setMission(view);
          setSimId(view.simulation_id);
          setStatus(view.sim_status);
        })
        .catch((e: Error) => setNotice(e.message));
    } else if (missionId) {
      void authedRequest(() => api.mission(missionId))
        .then(setMission)
        .catch((e: Error) => setNotice(e.message));
    }
  }, [missionId, token, judge]);

  // initial REST load once sim is known (authed only — WS fills the rest)
  useEffect(() => {
    if (judge || !simId) return;
    void (async () => {
      try {
        const [ev, det] = await Promise.all([
          authedRequest(() => api.events(simId, 0, MAX_EVENTS)),
          authedRequest(() => api.detections(simId)),
        ]);
        setEvents((prev) => dedupe(prev, ev.items));
        setDetections((prev) => {
          const ids = new Set(prev.map((d) => d.detection_id));
          return [...prev, ...det.filter((d) => !ids.has(d.detection_id))];
        });
      } catch (e) {
        setNotice((e as Error).message);
      }
    })();
  }, [simId, judge]);

  // merge WS frames
  useEffect(() => {
    if (judge) return;
    if (live.events.length > 0) setEvents((prev) => dedupe(prev, live.events));
    if (live.detections.length > 0) {
      setDetections((prev) => {
        const ids = new Set(prev.map((d) => d.detection_id));
        return [
          ...prev,
          ...live.detections.filter((d) => !ids.has(d.detection_id)),
        ];
      });
    }
    setStatus((s) =>
      s === live.status || live.status === "connecting" ? s : live.status,
    );
  }, [live, judge]);

  // score + judge-mode feed polling
  useEffect(() => {
    if (!simId) return;
    const tick = async () => {
      try {
        if (judge && tokenRef.current) {
          const [ev, det, sc] = await Promise.all([
            api.publicEvents(tokenRef.current, 0, MAX_EVENTS),
            api.publicDetections(tokenRef.current),
            api.publicScore(tokenRef.current),
          ]);
          setEvents(ev.items);
          setDetections(det);
          setScore(sc);
        } else {
          const sc = await authedRequest(() => api.missionScore(simId));
          setScore(sc);
        }
      } catch {
        /* transient — next tick retries */
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [simId, judge]);

  const start = useCallback(async () => {
    if (!missionId) return;
    setStarting(true);
    setNotice(null);
    try {
      const created = await authedRequest(() => api.missionStart(missionId));
      simIdRef.current = created.simulation_id;
      setSimId(created.simulation_id);
      setShareUrl(created.share_url);
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setStarting(false);
    }
  }, [missionId]);

  const execute = useCallback(
    async (detection: Detection, actionId: string, confirm: boolean) => {
      if (!simId) return;
      try {
        if (judge && tokenRef.current) {
          await api.publicExecute(
            tokenRef.current,
            detection.detection_id,
            actionId,
            {},
            confirm,
          );
        } else {
          await authedRequest(() =>
            api.execute(simId, detection.detection_id, actionId, {}, confirm),
          );
        }
        setLastAction({ action_id: actionId, executed_at: Date.now() });
      } catch (e) {
        setNotice((e as Error).message);
        throw e;
      }
    },
    [simId, judge],
  );

  return {
    mission,
    simId,
    starting,
    notice,
    shareUrl,
    status,
    events,
    detections,
    score,
    lastAction,
    start,
    execute,
  };
}
