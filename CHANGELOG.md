# Changelog

All notable changes to Losshound are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3] - 2026-07-09

Trust and clarity release: measurements now fail honestly, optimizer restores
are exact and retryable, and the interface distinguishes collecting, paused,
stale, and failed states from a healthy connection.

### Added
- Locale-independent active-interface discovery based on the effective Windows
  default route, shared by gateway, LAN, drop-attribution, and optimizer flows.
- Explicit loading, empty, and database-error states across the dashboard,
  History, Routes, LAN Monitor, and Export views.
- Windows executable version metadata and regression coverage for CLI argument
  validation, configuration corruption, subprocess cleanup, UI truth states,
  optimizer rollback, total outages, and multi-adapter behavior.

### Changed
- The LAN-discovery firewall rule is now off by default, requires explicit
  confirmation, and is created only for a packaged Losshound executable—never
  for a shared `python.exe` source interpreter.
- The dashboard and tray use configured diagnosis thresholds and share truthful
  collecting, healthy, warning, paused, error, and stale states.
- All top-level tabs remain reachable at the 1200 px minimum window width;
  keyboard focus and accessible control descriptions were also strengthened.
- QoS rules distinguish saved configuration from policies verified during the
  current session. A saved rule is retained when Windows cannot remove it.

### Fixed
- A disconnected interface can no longer match the word `connected` and skew
  drop/cable attribution; link speed is read from the selected route interface.
- A complete outage now records 100% loss and an unavailable bufferbloat grade
  instead of synthetic 999 ms samples and grade A. Non-finite measurements are
  persisted as strict JSON `null` values.
- Trace routes are complete only when the requested or resolved destination is
  reached, not merely when the last parsed hop has an IP address.
- Adaptive monitoring runs gateway/public probes concurrently with deadlines,
  so its fast cadence remains useful during timeout bursts.
- Optimizer results say Verified only after desired-state read-back. DNS backup,
  apply, rollback, and restore are adapter-scoped and preserve DHCP/static mode
  plus the full server order.
- Registry restores preserve exact value presence, verify every write/delete,
  and retain the backup whenever a step fails or cannot be verified.
- Malformed or wrongly typed configuration values fall back safely; settings
  saves no longer discard hidden timeout/logging values and are atomic.
- Failed `taskkill` operations fall back to direct termination, and the Windows
  Job Object now protects CLI subprocesses as well as GUI subprocesses.
- Corrected misleading labels such as Public IP, Packet logs, RTT-as-minimum,
  and STEP; initial startup no longer claims the network is already stable.

## [0.1.2] - 2026-07-02

### Added
- **Native ICMP pinger.** IPv4 targets are pinged through the Windows
  `IcmpSendEcho` API (no admin needed) instead of spawning `ping.exe`: no
  process per probe, no locale-dependent parsing, and sub-millisecond gateway
  RTT/jitter resolution. Hostname targets still fall back to `ping.exe`.
- **Adaptive monitoring cadence.** When a cycle sees loss or timeouts, sampling
  densifies to every 5s with a lighter probe count to capture the burst shape,
  then returns to the configured interval after 3 clean cycles. The status bar
  shows the effective interval.
- **Lag attribution ("blame the process").** On an RTT spike (2x the learned
  healthy baseline) or loss, the monitor samples interface throughput
  (`GetIfTable`) and active connections per process, then reports a verdict in
  the dashboard: local saturation (naming the likely app), external (ISP or
  route), or inconclusive. Saturation is judged against the line capacity
  measured by the load benchmark when available.

### Fixed
- **A stuck DNS lookup no longer fails checks for other hostnames.** The
  resolver in-flight guard is now per hostname; previously one hung lookup made
  every other hostname report failure, which could trigger false "DNS issue"
  diagnoses.
- **Load benchmark actually saturates the line again.** The download mirror
  list had rotted (tele2/hetzner gone) and 1 MB files caused reconnect churn,
  which produced misleadingly good bufferbloat grades. Replaced with large
  files on live CDNs; download threads also stop faster after the test window.
- **Cleaner shutdown windows.** The monitor thread's stop timeout now covers
  the route-check and attribution threads' own stop waits, avoiding hard
  terminations mid-write.
- **Local saved-state hardening.** QoS rules and optimizer restore backups now
  validate locally stored numeric/state fields before they can influence
  elevated Windows networking commands.

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

[0.1.3]: https://github.com/NoSelection/Losshound/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/NoSelection/Losshound/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/NoSelection/Losshound/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/NoSelection/Losshound/releases/tag/v0.1.0
