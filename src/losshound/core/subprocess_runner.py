"""Thread-interruption-safe subprocess runner.

Allows background worker QThreads to kill long-running command lines
(like ping or traceroute) cleanly and immediately when the thread or
application is requested to shut down.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from PySide6.QtCore import QThread

logger = logging.getLogger(__name__)

# Windows creation flag to prevent console window flashing
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def run_subprocess_interruptible(args: list[str], timeout_sec: float) -> tuple[str, str, int]:
    """Run an external command via subprocess.Popen in a thread-interruption-safe way.

    Checks for QThread interruption requests every 50ms and kills the process
    immediately if one is detected.

    Raises:
        InterruptedError: If thread interruption was requested.
        subprocess.TimeoutExpired: If the process runs longer than timeout_sec.
    """
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=CREATE_NO_WINDOW
    )
    start_time = time.monotonic()

    try:
        while True:
            # Check if process is finished
            ret = proc.poll()
            if ret is not None:
                stdout, stderr = proc.communicate()
                return stdout, stderr, ret

            # Check QThread interruption
            current_thread = QThread.currentThread()
            if current_thread and current_thread.isInterruptionRequested():
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise InterruptedError("Subprocess terminated due to thread interruption request.")

            # Check timeout
            if time.monotonic() - start_time > timeout_sec:
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise subprocess.TimeoutExpired(args, timeout_sec)

            time.sleep(0.05)
    except Exception:
        # Guarantee cleanup of subprocess on any other unexpected exception (e.g. GeneratorExit/KeyboardInterrupt)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        raise
