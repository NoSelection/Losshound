"""Smart tray-alert engine.

Stateful processor that turns a stream of Diagnosis objects into a stream
of AlertEvent objects, suitable for the system tray to display as toast
notifications. Handles state-transition detection, debouncing, severity
escalation, snooze, and persistence to the HistoryStore.
"""

from __future__ import annotations

# Implementation lives here. See plan Track B.
