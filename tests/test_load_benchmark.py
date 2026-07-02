import threading
import time

from losshound.core import load_benchmark


def test_generate_load_downloads_concurrently(monkeypatch):
    """All URLs must download in parallel — that's the point of a load test."""
    lock = threading.Lock()
    active: set[str] = set()
    peak_concurrency = 0

    def fake_download(url, result_holder, stop_event):
        nonlocal peak_concurrency
        with lock:
            active.add(url)
            peak_concurrency = max(peak_concurrency, len(active))
        time.sleep(0.15)
        with lock:
            active.discard(url)
        result_holder.update(bytes=1000, duration=0.15, url=url, success=True)

    monkeypatch.setattr(load_benchmark, "_download_file", fake_download)

    stop = threading.Event()
    holder: dict = {}
    load_benchmark._generate_load(["u1", "u2", "u3"], 0.5, stop, holder)

    assert peak_concurrency == 3
    assert holder["total_bytes"] >= 3000
    assert holder["best_speed"] > 0
    assert holder["best_url"] in {"u1", "u2", "u3"}
    # The generator signals its workers to stop once the deadline passes.
    assert stop.is_set()


def test_generate_load_respects_deadline(monkeypatch):
    def fake_download(url, result_holder, stop_event):
        # Simulate a download that polls the stop event like the real one.
        end = time.perf_counter() + 10
        while time.perf_counter() < end and not stop_event.is_set():
            time.sleep(0.02)
        result_holder.update(bytes=10, duration=0.1, url=url, success=True)

    monkeypatch.setattr(load_benchmark, "_download_file", fake_download)

    stop = threading.Event()
    holder: dict = {}
    start = time.perf_counter()
    load_benchmark._generate_load(["u1", "u2"], 0.4, stop, holder)
    elapsed = time.perf_counter() - start

    # Deadline 0.4s + join grace; nowhere near the 10s the download wanted.
    assert elapsed < 3.0
    assert holder["total_bytes"] == 20


def test_generate_load_handles_failing_url(monkeypatch):
    def fake_download(url, result_holder, stop_event):
        if url == "bad":
            result_holder.update(success=False, error="boom")
        else:
            result_holder.update(bytes=500, duration=0.1, url=url, success=True)
        time.sleep(0.05)

    monkeypatch.setattr(load_benchmark, "_download_file", fake_download)

    stop = threading.Event()
    holder: dict = {}
    load_benchmark._generate_load(["bad", "good"], 0.3, stop, holder)

    assert holder["total_bytes"] >= 500
    assert holder["best_url"] == "good"
