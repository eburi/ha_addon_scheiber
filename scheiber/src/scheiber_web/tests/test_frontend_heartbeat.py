import threading
import time

from scheiber_web.frontend_heartbeat import FrontendHeartbeatMonitor


def test_frontend_heartbeat_waits_for_last_browser_before_cleanup():
    cleanup_event = threading.Event()
    monitor = FrontendHeartbeatMonitor(autostart_watchdog=False)
    monitor.add_idle_callback(cleanup_event.set)

    try:
        monitor.heartbeat("browser-1", page="setup")
        monitor.heartbeat("browser-2", page="inspect")

        snapshot = monitor.disconnect("browser-1")
        assert snapshot["active_clients"] == 1
        assert cleanup_event.is_set() is False

        snapshot = monitor.disconnect("browser-2")
        assert snapshot["active_clients"] == 0
        assert cleanup_event.is_set() is True
    finally:
        monitor.shutdown()


def test_frontend_heartbeat_expires_stale_browser_and_runs_cleanup():
    cleanup_event = threading.Event()
    monitor = FrontendHeartbeatMonitor(
        timeout_seconds=0.02,
        sweep_interval_seconds=0.005,
    )
    monitor.add_idle_callback(cleanup_event.set)

    try:
        monitor.heartbeat("browser-1", page="setup")

        deadline = time.time() + 0.2
        while time.time() < deadline and not cleanup_event.is_set():
            time.sleep(0.005)

        assert cleanup_event.is_set() is True
        assert monitor.snapshot()["active_clients"] == 0
    finally:
        monitor.shutdown()
