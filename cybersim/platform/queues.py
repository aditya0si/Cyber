"""Platform-level Celery app (docs/03 §6, docs/04 §2.10, docs/21 Task 2.2)."""

from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

#: A single Celery app drives sim + analyst + ops queues, with per-queue priorities
#: provided by queue name (sims > analyst > ops). Concurrency caps and autoscaling
#: are set on the worker launch, not here.
celery_app = Celery(
    "cybersim",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_default_queue="sims",
    task_queues=("sims", "analyst", "ops"),
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "cybersim.simulation.tasks.run_simulation": {"queue": "sims"},
        "cybersim.analyst.tasks.*": {"queue": "analyst"},
        "cybersim.tools.*": {"queue": "ops"},
    },
)


__all__ = ["celery_app"]
