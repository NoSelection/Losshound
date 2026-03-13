from __future__ import annotations

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="losshound",
        description="Losshound — Lightweight Windows network diagnosis tool",
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
        help="Save report to file instead of printing",
    )

    args = parser.parse_args()

    from losshound.core.config import load_config
    config = load_config(args.config)

    if args.log_level:
        config.log_level = args.log_level

    from losshound.core.logger import setup_logging
    setup_logging(config.log_level)

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
    from losshound.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Losshound")
    app.setApplicationVersion("0.1.0")

    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
