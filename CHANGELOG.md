# Changelog

All notable changes to Losshound are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-06-29

Reliability release: the monitor no longer stalls, worker threads shut down
cleanly, and several actions that only *looked* like they worked now actually do.

### Fixed
- **Monitor timers are now driven from the worker thread.** Timer config and
  shutdown calls hop into the worker via queued signals, so changing the ping or
  route interval in Settings actually takes effect (previously the change was
  silently dropped with a cross-thread Qt warning).
- **Route checks no longer block monitoring.** `tracert` runs in its own thread,
  so ping cycles and the status countdown stay responsive even during a slow
  (up to ~90s) trace.
- **DNS resolution no longer leaks threads.** A single bounded resolver replaces
  the per-check thread pool; a stalled lookup past its timeout no longer leaves a
  background thread alive, and overlapping checks are skipped while one is pending.
- **"Run Now" actually runs a monitor cycle** instead of only rewinding the
  on-screen countdown.
- **Thread-safe database access for reports.** The ISP report and PDF workers open
  their own `HistoryStore` connection instead of sharing the GUI's, avoiding
  intermittent SQLite errors and UI stutter.
- **LAN scan no longer leaks a database connection** — the per-scan
  `HistoryStore` is now closed via a context manager.
- **Load benchmark downloads run concurrently** as documented, instead of
  sequentially, so bufferbloat measurements reflect a properly loaded link.

### Added
- `HistoryStore` supports use as a context manager (`with HistoryStore(...)`).
- Settings changes now propagate to the LAN Monitor tab.

## [0.1.0]

Initial public release.

[0.1.1]: https://github.com/NoSelection/Losshound/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/NoSelection/Losshound/releases/tag/v0.1.0
