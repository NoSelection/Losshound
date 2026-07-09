from __future__ import annotations

import argparse
import os
import sys

from losshound import __version__


def _needs_console(argv: list[str] | tuple[str, ...] | None = None) -> bool:
    """Return whether a windowed build was invoked from the command line.

    A normal Explorer launch has no arguments and should remain console-free.
    Any supplied argument can lead to argparse output (including an error for a
    typo), so packaged command-line launches need real standard streams.
    """

    return len(sys.argv if argv is None else argv) > 1


def _ensure_command_line_streams(
    argv: list[str] | tuple[str, ...] | None = None,
) -> None:
    """Restore stdio for command-line use of PyInstaller's windowed build.

    PyInstaller intentionally sets ``sys.stdout`` and ``sys.stderr`` to
    ``None`` in a windowed executable.  argparse and every CLI command expect
    writable streams, so attach to the caller's console (or create one when
    launched outside a terminal) before parsing arguments.
    """

    if (
        sys.platform != "win32"
        or not getattr(sys, "frozen", False)
        or not _needs_console(argv)
    ):
        return

    console_available = False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.AttachConsole.argtypes = [wintypes.DWORD]
        kernel32.AttachConsole.restype = wintypes.BOOL
        kernel32.AllocConsole.argtypes = []
        kernel32.AllocConsole.restype = wintypes.BOOL

        # ATTACH_PARENT_PROCESS is DWORD(-1). ERROR_ACCESS_DENIED means the
        # process already has a console, which is also a usable outcome.
        if kernel32.AttachConsole(0xFFFFFFFF):
            console_available = True
        elif ctypes.get_last_error() == 5:
            console_available = True
        else:
            console_available = bool(kernel32.AllocConsole())
    except (AttributeError, OSError):
        # Stream fallbacks below still prevent a secondary crash if console
        # attachment is unavailable in an unusual host environment.
        console_available = False

    def _stream(name: str, mode: str):
        target = name if console_available else os.devnull
        try:
            return open(
                target,
                mode,
                encoding="utf-8",
                errors="replace",
                buffering=1,
            )
        except OSError:
            return open(
                os.devnull,
                mode,
                encoding="utf-8",
                errors="replace",
            )

    if not callable(getattr(sys.stdin, "read", None)):
        sys.stdin = _stream("CONIN$", "r")
    if not callable(getattr(sys.stdout, "write", None)):
        sys.stdout = _stream("CONOUT$", "w")
    if not callable(getattr(sys.stderr, "write", None)):
        sys.stderr = _stream("CONOUT$", "w")


def main():
    _ensure_command_line_streams()

    parser = argparse.ArgumentParser(
        prog="losshound",
        description="Losshound - Lightweight Windows network diagnosis tool",
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="Run in CLI mode (no GUI)",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to configuration file",
    )
    parser.add_argument(
        "--log-level", type=str, default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    # Optimizer subcommands
    sub = parser.add_subparsers(dest="command")

    opt_parser = sub.add_parser("optimize", help="Optimize network performance")
    opt_parser.add_argument(
        "--skip-dns", action="store_true",
        help="Skip DNS benchmark and optimization",
    )
    opt_parser.add_argument(
        "--apply-dns", action="store_true",
        help="Allow optimize to change DNS servers after benchmarking",
    )
    opt_parser.add_argument(
        "--skip-mtu", action="store_true",
        help="Skip MTU discovery and optimization",
    )

    sub.add_parser("dns-benchmark", help="Benchmark DNS servers")
    sub.add_parser("net-status", help="Show current network optimization status")
    sub.add_parser("restore", help="Restore network settings from backup")

    bench_parser = sub.add_parser("benchmark", help="Run network performance benchmark")
    bench_parser.add_argument(
        "--label", type=str, default="snapshot",
        help="Label for this benchmark (e.g. 'before' or 'after')",
    )
    bench_parser.add_argument(
        "--pings", type=int, default=20,
        help="Number of pings per target (default: 20)",
    )
    sub.add_parser("compare", help="Compare last 'before' vs 'after' benchmarks")

    load_bench_parser = sub.add_parser(
        "load-benchmark", help="Benchmark under network load (bufferbloat, throughput)",
    )
    load_bench_parser.add_argument(
        "--label", type=str, default="snapshot",
        help="Label for this benchmark (e.g. 'before' or 'after')",
    )
    sub.add_parser("load-compare", help="Compare before vs after load benchmarks")

    score_parser = sub.add_parser("score", help="Run benchmark and show network score")
    score_parser.add_argument(
        "--pings", type=int, default=20,
        help="Number of pings per target (default: 20)",
    )

    trends_parser = sub.add_parser("trends", help="Show network performance trends")
    trends_parser.add_argument(
        "--hours", type=int, default=168,
        help="Lookback period in hours (default: 168 = 7 days)",
    )

    history_parser = sub.add_parser("history", help="List recent benchmark snapshots with scores")
    history_parser.add_argument(
        "--count", type=int, default=20,
        help="Number of entries to show (default: 20)",
    )

    sub.add_parser("wifi", help="Run WiFi diagnostics (channel scan, signal, interference)")

    drop_parser = sub.add_parser(
        "drop-analyze",
        help="Analyze connectivity drops (jammer/ISP/cable diagnosis)",
    )
    drop_parser.add_argument(
        "--duration", type=int, default=120,
        help="Monitoring duration in seconds (default: 120)",
    )
    drop_parser.add_argument(
        "--interval", type=float, default=3.0,
        help="Polling interval in seconds (default: 3.0)",
    )
    drop_parser.add_argument(
        "--wan-target", type=str, default="8.8.8.8",
        help="Public IP to ping for WAN check (default: 8.8.8.8)",
    )

    qos_parser = sub.add_parser("qos", help="Add a per-app QoS priority rule")
    qos_parser.add_argument("app", help="Application name or path (e.g. chrome.exe)")
    qos_parser.add_argument(
        "--priority", type=str, default="High",
        choices=["Realtime", "High", "Normal", "Low", "Bulk"],
        help="Priority preset (default: High)",
    )
    sub.add_parser("qos-list", help="List all QoS rules and active policies")
    sub.add_parser("qos-clear", help="Remove all Losshound QoS policies")

    isp_parser = sub.add_parser("isp-report", help="Generate comprehensive ISP report")
    isp_parser.add_argument(
        "--hours", type=int, default=24,
        help="Report period in hours (default: 24)",
    )
    isp_parser.add_argument(
        "--output", type=str, default=None,
        help="Save text report to file instead of printing",
    )
    isp_parser.add_argument(
        "--pdf", type=str, default=None,
        help="Save report as a PDF to the given path (overrides --output)",
    )

    args = parser.parse_args()
    if args.command == "drop-analyze":
        if args.duration <= 0:
            parser.error("drop-analyze --duration must be greater than 0 seconds")
        if args.interval < 1.0:
            parser.error("drop-analyze --interval must be at least 1.0 seconds")
    elif args.command in {"benchmark", "score"} and args.pings <= 0:
        parser.error(f"{args.command} --pings must be greater than 0")
    elif args.command == "trends" and args.hours <= 0:
        parser.error("trends --hours must be greater than 0")
    elif args.command == "history" and args.count <= 0:
        parser.error("history --count must be greater than 0")
    elif args.command == "isp-report" and args.hours <= 0:
        parser.error("isp-report --hours must be greater than 0")

    from losshound.core.config import load_config
    config = load_config(args.config)

    if args.log_level:
        config.log_level = args.log_level

    from losshound.core.logger import setup_logging
    setup_logging(config.log_level)

    # Cover GUI and CLI subprocesses alike. On non-Windows platforms this is a
    # safe no-op; on Windows it prevents ping/tracert/netsh children surviving
    # an abrupt parent exit.
    from losshound.core.job_object import install_kill_on_close_job
    install_kill_on_close_job()

    if args.command:
        from losshound.cli.optimizer_cli import run_optimizer_command
        run_optimizer_command(args)
    elif args.cli:
        from losshound.cli.runner import run_cli
        run_cli(config)
    else:
        _run_gui(config)


def _run_gui(config):
    from PySide6.QtWidgets import QApplication
    from losshound.core.firewall import ensure_lan_discovery_firewall_rules
    from losshound.gui.branding import app_icon
    from losshound.gui.main_window import MainWindow

    # The firewall rule is opt-in. Once the user has explicitly enabled it in
    # Settings, an elevated packaged build may reconcile a moved executable.
    if config.lan_discovery_firewall_enabled:
        ensure_lan_discovery_firewall_rules()

    app = QApplication(sys.argv)
    app.setApplicationName("Losshound")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())

    window = MainWindow(config)
    app.aboutToQuit.connect(window.shutdown_all)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
