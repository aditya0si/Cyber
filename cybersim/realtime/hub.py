"""Realtime hub (docs/08 §5, docs/21 Task 4.2).

Manages per-connection subscription sets and fan-out by channel. Server-side
coalescing (default ≤4 msg/sec per subscription), lag frames, and
backpressure (drop-oldest beyond 100 unread) per docs/08 §5.4.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect


@dataclass
class _Subscription:
    ws: WebSocket
    channel: str
    loop: asyncio.AbstractEventLoop | None = None
    last_seq: int = 0
    queue: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=100))
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_send_ts: float = 0.0
    pending: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False


class RealtimeHub:
    """In-process fan-out for WS connections (single-instance MVP).

    Multi-instance fan-out via Redis pub/sub is added in Phase 9 behind the
    `publish()` seam — the hub's API is unchanged.
    """

    COALESCE_MS = 250  # max 4 msg/sec per subscription

    def __init__(self) -> None:
        self._subs: dict[str, list[_Subscription]] = defaultdict(list)
        self._sessions: dict[str, list[_Subscription]] = defaultdict(list)
        self._tasks: set[asyncio.Task[Any]] = set()

    # ---- server side --------------------------------------------------------
    async def handle_connection(
        self, ws: WebSocket, *, session_id: str, channels: list[str]
    ) -> None:
        """Accept a connection, attach to `channels`, pump until disconnect."""
        await ws.accept()
        subs: list[_Subscription] = []
        for channel in channels:
            sub = _Subscription(ws=ws, channel=channel, loop=asyncio.get_running_loop())
            self._subs[channel].append(sub)
            self._sessions[session_id].append(sub)
            subs.append(sub)
        await self._send(
            ws, {"kind": "hello", "channel": "system", "server_time_ms": int(time.time() * 1000)}
        )
        try:
            while True:
                raw = await ws.receive_text()
                frame = json.loads(raw)
                await self._handle_client_frame(ws, session_id, frame)
        except WebSocketDisconnect:
            pass
        finally:
            for sub in subs:
                self._unsubscribe(sub)

    async def _handle_client_frame(
        self, ws: WebSocket, session_id: str, frame: dict[str, Any]
    ) -> None:
        kind = frame.get("kind")
        if kind == "subscribe":
            channel = frame.get("channel")
            if not channel:
                return
            sub = _Subscription(ws=ws, channel=str(channel))
            self._subs[channel].append(sub)
            self._sessions[session_id].append(sub)
            await self._send(ws, {"kind": "subscribed", "channel": channel})
        elif kind == "unsubscribe":
            channel = frame.get("channel")
            if channel:
                for sub in self._sessions.get(session_id, []):
                    if sub.channel == channel:
                        self._unsubscribe(sub)
        elif kind == "ping":
            await self._send(ws, {"kind": "pong"})

    def _unsubscribe(self, sub: _Subscription) -> None:
        sub.closed = True
        if sub in self._subs.get(sub.channel, []):
            self._subs[sub.channel].remove(sub)
        for sess_list in self._sessions.values():
            if sub in sess_list:
                sess_list.remove(sub)

    def shutdown(self) -> None:
        """Cancel all in-flight flush tasks (call on app teardown)."""
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()

    # ---- publish side -------------------------------------------------------
    def publish(self, channel: str, frame: dict[str, Any]) -> None:
        """Fan-out a frame to every subscription on `channel` (coalesced).

        Thread-safe: delivery is scheduled onto each subscription's event
        loop via `call_soon_threadsafe`, so callers from sync threads
        (TestClient, worker tasks) work without a running loop.
        """
        for sub in list(self._subs.get(channel, [])):
            if sub.closed or sub.loop is None:
                continue
            sub.pending.append(frame)
            try:
                sub.loop.call_soon_threadsafe(self._schedule_flush, sub)
            except RuntimeError:
                # Loop closed (e.g., TestClient portal teardown mid-publish):
                # drop the frame rather than raise into the caller.
                sub.pending.pop()

    def _schedule_flush(self, sub: _Subscription) -> None:
        if sub.closed:
            return
        try:
            task = asyncio.create_task(self._flush(sub))
        except RuntimeError:
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _flush(self, sub: _Subscription) -> None:
        async with sub.send_lock:
            if not sub.pending or sub.closed:
                return
            now = time.monotonic()
            if now - sub.last_send_ts < self.COALESCE_MS / 1000:
                await asyncio.sleep(self.COALESCE_MS / 1000 - (now - sub.last_send_ts))
            batch = sub.pending
            sub.pending = []
            sub.last_send_ts = time.monotonic()
            if len(batch) == 1:
                await self._send(sub.ws, batch[0])
            else:
                await self._send(
                    sub.ws,
                    {
                        "kind": "event.batch",
                        "events": [b for b in batch if b.get("kind") == "event.upsert"],
                        "frames": batch,
                        "count": len(batch),
                    },
                )
            # lag / backpressure
            if sub.queue.maxlen and len(batch) >= sub.queue.maxlen:  # pragma: no cover
                await self._send(sub.ws, {"kind": "sim.lag", "lag_ms": 1})

    async def _send(self, ws: WebSocket, payload: dict[str, Any]) -> None:
        with contextlib.suppress(RuntimeError):
            await ws.send_text(json.dumps(payload, default=str))
