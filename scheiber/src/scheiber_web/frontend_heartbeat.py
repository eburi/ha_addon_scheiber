"""Browser heartbeat tracking for frontend-owned setup services."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional


class FrontendHeartbeatMonitor:
    """Track active browser sessions and stop frontend-only activity on idle."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 900.0,
        sweep_interval_seconds: float = 2.0,
        logger: Optional[logging.Logger] = None,
        autostart_watchdog: bool = True,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.sweep_interval_seconds = sweep_interval_seconds
        self.logger = logger or logging.getLogger(__name__)
        self._lock = threading.RLock()
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._idle_callbacks: List[Callable[[], Any]] = []
        self._stop_event = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None

        if autostart_watchdog:
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop,
                name="scheiber-frontend-heartbeat",
                daemon=True,
            )
            self._watchdog_thread.start()

    def add_idle_callback(self, callback: Callable[[], Any]) -> None:
        """Register a callback that runs when the last browser session expires."""
        with self._lock:
            if callback not in self._idle_callbacks:
                self._idle_callbacks.append(callback)

    def heartbeat(self, client_id: str, page: Optional[str] = None) -> Dict[str, Any]:
        """Refresh a browser session and return the current monitor snapshot."""
        now = time.time()
        with self._lock:
            self._sessions[client_id] = {
                "client_id": client_id,
                "page": page,
                "last_seen_at": now,
            }
            return self._snapshot_locked(now)

    def disconnect(self, client_id: str) -> Dict[str, Any]:
        """Remove a browser session and trigger idle cleanup when it was the last one."""
        callbacks: List[Callable[[], Any]] = []
        now = time.time()
        with self._lock:
            had_active_clients = bool(self._sessions)
            self._sessions.pop(client_id, None)
            if had_active_clients and not self._sessions:
                callbacks = list(self._idle_callbacks)
            snapshot = self._snapshot_locked(now)

        self._run_idle_callbacks(callbacks)
        return snapshot

    def snapshot(self) -> Dict[str, Any]:
        """Return the current frontend heartbeat state after pruning expired sessions."""
        return self._prune_and_snapshot(time.time())

    def shutdown(self) -> None:
        """Stop the background watchdog used for session expiry."""
        self._stop_event.set()
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=1.0)

    def _watchdog_loop(self) -> None:
        while not self._stop_event.wait(self.sweep_interval_seconds):
            self._prune_and_snapshot(time.time())

    def _prune_and_snapshot(self, now: float) -> Dict[str, Any]:
        callbacks: List[Callable[[], Any]] = []
        with self._lock:
            had_active_clients = bool(self._sessions)
            expiry_cutoff = now - self.timeout_seconds
            expired_client_ids = [
                client_id
                for client_id, session in self._sessions.items()
                if session["last_seen_at"] < expiry_cutoff
            ]
            for client_id in expired_client_ids:
                self._sessions.pop(client_id, None)
                self.logger.info(
                    "Frontend heartbeat expired for browser session %s", client_id
                )

            if had_active_clients and not self._sessions:
                callbacks = list(self._idle_callbacks)

            snapshot = self._snapshot_locked(now)

        self._run_idle_callbacks(callbacks)
        return snapshot

    def _snapshot_locked(self, now: float) -> Dict[str, Any]:
        last_client_seen_at = None
        if self._sessions:
            last_client_seen_at = max(
                session["last_seen_at"] for session in self._sessions.values()
            )

        return {
            "active_clients": len(self._sessions),
            "timeout_seconds": self.timeout_seconds,
            "last_client_seen_at": last_client_seen_at,
            "clients": [
                {
                    "client_id": client_id,
                    "page": session["page"],
                    "last_seen_at": session["last_seen_at"],
                    "expires_in_seconds": max(
                        0.0,
                        round(
                            session["last_seen_at"] + self.timeout_seconds - now,
                            3,
                        ),
                    ),
                }
                for client_id, session in sorted(self._sessions.items())
            ],
        }

    def _run_idle_callbacks(self, callbacks: List[Callable[[], Any]]) -> None:
        if not callbacks:
            return

        self.logger.info(
            "No active setup browsers remain; stopping frontend-only services"
        )
        for callback in callbacks:
            try:
                callback()
            except Exception:
                self.logger.exception("Failed to stop frontend-only service")
