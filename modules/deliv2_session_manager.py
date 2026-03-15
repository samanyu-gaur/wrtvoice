"""
Deliverable 2 - Session Manager
================================
Multi-user session management and inference concurrency control for the
Socratic Oracle platform.

What this does:
    Replaces the single-user global session dict with a proper session store
    that can track many simultaneous users.  Each user gets an isolated session
    with its own conversation history and state.  An asyncio.Semaphore caps
    GPU inference requests so the server degrades gracefully under load rather
    than crashing or timing out.

What I learned (as a Y1 CompEng student):
    - asyncio.Semaphore is surprisingly powerful for rate-limiting concurrent
      work without pulling in heavyweight libs like Celery or Redis.
    - Stateless REST patterns (each request carries a session_id) are way
      simpler to reason about than sticky WebSocket state when you are
      scaling beyond one user.
    - Python dicts are fine as an in-process session store for a pilot of
      250 students; you only need Redis/Postgres when the process can crash
      and you need persistence across restarts.

Author: Akshay T P
Date: March 2025
"""

import asyncio
import uuid
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Tuple

from modules.conversation_manager import ConversationManager

# ---------------------------------------------------------------------------
# DESIGN DECISION: In-memory dict vs. Redis vs. database-backed sessions
# ---------------------------------------------------------------------------
# We chose a plain Python dict guarded by an asyncio.Lock.
#
# Alternative 1 - Redis:
#   Pros:  survives process restarts, works across multiple server processes.
#   Cons:  adds an external dependency; for a 250-student pilot running on a
#          single FastAPI worker, the extra infrastructure is not justified.
#
# Alternative 2 - SQLite / PostgreSQL:
#   Pros:  durable, queryable, easy to back up.
#   Cons:  overkill when sessions are short-lived tutoring conversations.
#          We already persist finished conversations as JSON files, so we
#          only need in-memory state for *active* sessions.
#
# Alternative 3 - Encrypted JWT tokens (session data on the client):
#   Pros:  truly stateless server -- no server-side store at all.
#   Cons:  tokens grow large quickly with conversation history, cannot be
#          revoked, and parsing a fat JWT on every request is wasteful.
#
# Verdict: dict + Lock is the simplest thing that works for our scale.
#          If we later run multiple workers behind a load balancer, move
#          to Redis.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DESIGN DECISION: asyncio.Semaphore vs. Celery vs. custom thread pool
# ---------------------------------------------------------------------------
# We chose asyncio.Semaphore to cap concurrent inference calls.
#
# Alternative 1 - Celery + RabbitMQ/Redis:
#   Pros:  industry-standard task queue, retries, monitoring dashboard.
#   Cons:  massive operational overhead (broker, worker processes, config).
#          For a pilot that caps at 10 concurrent GPU requests, this is
#          bringing a tank to a knife fight.
#
# Alternative 2 - ThreadPoolExecutor:
#   Pros:  built-in, simple.
#   Cons:  mixing threads with asyncio is error-prone; the Ollama client
#          already uses aiohttp, so staying in the async world is cleaner.
#
# Alternative 3 - External rate limiter (nginx, Traefik):
#   Pros:  offloads rate-limiting to infra layer.
#   Cons:  does not give us queue-position feedback per user.
#
# Verdict: Semaphore gives us concurrency control AND lets us count how
#          many slots are taken, so we can report queue position to users.
# ---------------------------------------------------------------------------


class SessionManager:
    """
    Manages multiple user sessions and throttles GPU inference requests.

    Usage:
        manager = SessionManager(max_concurrent_inferences=10)

        # Create a session when a user connects
        session_id = manager.create_session(pdf_context, pdf_metadata)

        # Before calling the LLM, acquire an inference slot
        async with manager.inference_slot(session_id):
            response = await ollama_client.generate(...)

        # When the user disconnects
        manager.remove_session(session_id)
    """

    def __init__(self, max_concurrent_inferences: int = 10,
                 conversation_storage_dir: str = "conversations"):
        """
        Args:
            max_concurrent_inferences:
                Hard cap on how many LLM inference calls can run at once.
                Anything beyond this is held in a FIFO queue.
            conversation_storage_dir:
                Where finished conversation JSON files are saved.
        """
        # -- Session store --
        # Maps session_id -> session dict.  Each dict looks like:
        # {
        #     "session_id": str,
        #     "created_at": datetime,
        #     "last_active": datetime,
        #     "pdf_context": str,
        #     "pdf_metadata": dict,
        #     "conversation_manager": ConversationManager,
        #     "whisper_stt": None | WhisperSTT,
        #     "state": "idle" | "listening" | "inferring",
        # }
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

        # -- Concurrency control --
        self._max_concurrent = max_concurrent_inferences
        self._semaphore = asyncio.Semaphore(max_concurrent_inferences)

        # Track how many inference slots are currently occupied so we can
        # report it on the admin dashboard without poking at semaphore
        # internals (which are technically private).
        self._active_inferences: int = 0
        self._inference_lock = asyncio.Lock()

        # Simple FIFO queue depth counter (incremented when a coroutine
        # blocks on the semaphore, decremented when it acquires).
        self._queue_depth: int = 0
        self._queue_lock = asyncio.Lock()

        # Average inference latency (exponential moving average) -- used
        # to give users an estimated wait time when they are queued.
        self._avg_latency: float = 5.0  # start with a 5-second guess
        self._latency_alpha: float = 0.3  # EMA smoothing factor

        self._storage_dir = conversation_storage_dir

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def create_session(self, pdf_context: str = "",
                             pdf_metadata: Optional[Dict] = None) -> str:
        """
        Create a new user session.  Returns a unique session ID that the
        client must include in all subsequent requests.
        """
        session_id = str(uuid.uuid4())
        conv_manager = ConversationManager(storage_dir=self._storage_dir)

        if pdf_context:
            conv_manager.start_session(
                pdf_context=pdf_context,
                pdf_metadata=pdf_metadata
            )

        session = {
            "session_id": session_id,
            "created_at": datetime.now(timezone.utc),
            "last_active": datetime.now(timezone.utc),
            "pdf_context": pdf_context,
            "pdf_metadata": pdf_metadata or {},
            "conversation_manager": conv_manager,
            "whisper_stt": None,
            "state": "idle",
        }

        async with self._lock:
            self._sessions[session_id] = session

        return session_id

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a session by ID, or None if it does not exist."""
        async with self._lock:
            session = self._sessions.get(session_id)
        if session:
            session["last_active"] = datetime.now(timezone.utc)
        return session

    async def remove_session(self, session_id: str) -> bool:
        """
        Remove a session (e.g. when the user ends their conversation).
        Returns True if the session existed.
        """
        async with self._lock:
            removed = self._sessions.pop(session_id, None)
        return removed is not None

    async def list_sessions(self) -> list:
        """Return a summary list of all active sessions (for admin use)."""
        async with self._lock:
            sessions_snapshot = list(self._sessions.values())
        return [
            {
                "session_id": s["session_id"],
                "created_at": s["created_at"].isoformat(),
                "last_active": s["last_active"].isoformat(),
                "state": s["state"],
                "message_count": len(
                    s["conversation_manager"].conversation
                ),
            }
            for s in sessions_snapshot
        ]

    # ------------------------------------------------------------------
    # Concurrency control
    # ------------------------------------------------------------------

    class _InferenceSlot:
        """
        Async context manager that acquires an inference slot from the
        semaphore and tracks queue depth / active count for the dashboard.
        """

        def __init__(self, manager: "SessionManager",
                     session_id: str):
            self._manager = manager
            self._session_id = session_id
            self._start_time: float = 0.0

        async def __aenter__(self):
            mgr = self._manager

            # Mark ourselves as queued if we cannot acquire immediately.
            acquired = mgr._semaphore._value > 0  # peek (not atomic, but
            # only used for the dashboard counter -- the semaphore itself
            # is the source of truth for correctness).
            if not acquired:
                async with mgr._queue_lock:
                    mgr._queue_depth += 1

            await mgr._semaphore.acquire()

            # If we were queued, decrement the queue counter now.
            if not acquired:
                async with mgr._queue_lock:
                    mgr._queue_depth = max(0, mgr._queue_depth - 1)

            async with mgr._inference_lock:
                mgr._active_inferences += 1

            # Mark session state
            session = await mgr.get_session(self._session_id)
            if session:
                session["state"] = "inferring"

            self._start_time = time.monotonic()
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            mgr = self._manager

            elapsed = time.monotonic() - self._start_time
            # Update the running average latency (EMA)
            mgr._avg_latency = (
                mgr._latency_alpha * elapsed
                + (1 - mgr._latency_alpha) * mgr._avg_latency
            )

            async with mgr._inference_lock:
                mgr._active_inferences = max(0,
                                              mgr._active_inferences - 1)

            mgr._semaphore.release()

            session = await mgr.get_session(self._session_id)
            if session:
                session["state"] = "idle"

            return False  # do not suppress exceptions

    def inference_slot(self, session_id: str) -> "_InferenceSlot":
        """
        Return an async context manager that blocks until an inference
        slot is available.

        Usage:
            async with session_manager.inference_slot(sid):
                result = await ollama.generate(...)

        If all slots are occupied, the caller is held in a FIFO queue.
        The admin dashboard can read queue_depth and estimated_wait to
        show users their position.
        """
        return self._InferenceSlot(self, session_id)

    # ------------------------------------------------------------------
    # Dashboard metrics
    # ------------------------------------------------------------------

    async def get_stats(self) -> Dict[str, Any]:
        """
        Return a snapshot of system metrics for the admin dashboard.

        Returns a dict with:
            active_sessions     -- number of users with open sessions
            active_inferences   -- inference calls currently running
            max_inferences      -- configured cap
            queue_depth         -- requests waiting for a slot
            estimated_wait_sec  -- rough wait time for a queued request
            avg_latency_sec     -- EMA of recent inference durations
        """
        async with self._lock:
            session_count = len(self._sessions)

        async with self._inference_lock:
            active = self._active_inferences

        async with self._queue_lock:
            queued = self._queue_depth

        estimated_wait = queued * self._avg_latency

        return {
            "active_sessions": session_count,
            "active_inferences": active,
            "max_inferences": self._max_concurrent,
            "queue_depth": queued,
            "estimated_wait_sec": round(estimated_wait, 1),
            "avg_latency_sec": round(self._avg_latency, 2),
        }

    async def get_queue_position(self, session_id: str) -> Dict[str, Any]:
        """
        Return the approximate queue position for a given session.
        If the session is not queued, position is 0.

        This is intentionally approximate -- the exact FIFO ordering
        is managed by the semaphore internally. We report the total
        queue depth as a proxy, which is honest enough for a status
        message like 'you are in queue, position ~X'.
        """
        # ---------------------------------------------------------------------------
        # DESIGN DECISION: approximate position vs. exact ordered queue
        # ---------------------------------------------------------------------------
        # We report the total queue depth as the user's position, which is
        # slightly imprecise -- two users who enter the queue simultaneously
        # both see "position 3" if there are 3 ahead of them.
        #
        # Alternative: maintain an explicit ordered list and assign positions.
        #   Pros:  perfectly accurate.
        #   Cons:  adds bookkeeping and another lock; for a pilot with modest
        #          concurrency, the approximation is fine.
        #
        # Verdict: good enough for now.  Exact ordering matters more when
        #          you have thousands of concurrent users.
        # ---------------------------------------------------------------------------
        async with self._queue_lock:
            position = self._queue_depth

        return {
            "session_id": session_id,
            "position": position,
            "estimated_wait_sec": round(position * self._avg_latency, 1),
        }


# ---------------------------------------------------------------------------
# FUTURE IMPROVEMENTS (if we had more time)
# ---------------------------------------------------------------------------
# 1. Session expiry / garbage collection:
#    Right now sessions live until explicitly removed.  A background task
#    that reaps sessions inactive for >30 minutes would prevent memory leaks
#    during long deployments.
#
# 2. Persistent session store (Redis):
#    If we deploy behind multiple FastAPI workers with gunicorn, each worker
#    has its own dict.  Moving to Redis gives us a shared session store and
#    also survives process restarts.
#
# 3. Priority queue:
#    All users currently share a single FIFO.  For a campus deployment we
#    might want priority lanes (e.g. students with an imminent deadline get
#    bumped up, or TA/instructor queries skip the queue).
#
# 4. Per-user rate limiting:
#    A single student could hammer the API and monopolize inference slots.
#    Adding a per-session rate limit (e.g. max 2 requests/minute) would be
#    fairer under high load.
#
# 5. Websocket-based queue notifications:
#    Instead of the client polling for queue position, push updates over a
#    lightweight WebSocket so the UI updates in real time.
# ---------------------------------------------------------------------------
