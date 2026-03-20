from __future__ import annotations

import io
import queue
import threading
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Dict, Optional

from dna.runtime.app import DNAApp


class _QueueWriter(io.TextIOBase):
    def __init__(self, output_queue: "queue.Queue[dict]"):
        self._queue = output_queue
        self._buffer = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._buffer += s
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self._queue.put({"type": "log", "message": line})
        return len(s)

    def flush(self) -> None:
        if self._buffer.strip():
            self._queue.put({"type": "log", "message": self._buffer.strip()})
        self._buffer = ""


class AppRunner:
    def __init__(self):
        self._queue: "queue.Queue[dict]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    def start(self, config: Dict[str, Any]) -> bool:
        with self._lock:
            if self.is_running():
                return False
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_worker, args=(dict(config),), daemon=True)
            self._thread.start()
            self._queue.put({"type": "state", "state": "running"})
            return True

    def request_stop(self):
        self._stop_event.set()

    def drain_events(self) -> list[dict]:
        events: list[dict] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    def _run_worker(self, config: Dict[str, Any]):
        writer = _QueueWriter(self._queue)

        def on_event(name: str, payload: Dict[str, Any]):
            self._queue.put({"type": "event", "name": name, "payload": dict(payload)})

        try:
            with redirect_stdout(writer), redirect_stderr(writer):
                app = DNAApp(config)
                app.run(should_stop=self._stop_event.is_set, on_event=on_event)
        except Exception as exc:
            self._queue.put({"type": "log", "message": f"[ERROR] Runner crashed: {exc}"})
        finally:
            writer.flush()
            self._queue.put({"type": "state", "state": "stopped"})
