"""CLI interface for the network optimizer."""

from __future__ import annotations

import sys


def run_optimizer_command(args):
    """Dispatch optimizer subcommands."""
    if args.command in ("benchmark", "compare", "load-benchmark", "load-compare"):
        if args.command == "benchmark":
            _cmd_benchmark(label=args.label, ping_count=args.pings)
        elif args.command == "compare":
            _cmd_compare()
        elif args.command == "load-benchmark":
            _cmd_load_benchmark(label=args.label)
        elif args.command == "load-compare":
            _cmd_load_compare()
        return

    from losshound.core.optimizer import NetworkOptimizer

    opt = NetworkOptimizer()

    if args.command == "optimize":
        _cmd_optimize(opt, skip_dns=args.skip_dns, skip_mtu=args.skip_mtu)
    elif args.command == "dns-benchmark":
        _cmd_dns_benchmark(opt)
    elif args.command == "net-status":
        _cmd_status(opt)
    elif args.command == "restore":
        _cmd_restore(opt)


def _cmd_optimize(opt, *, skip_dns: bool, skip_mtu: bool):
    """Run full network optimization."""
    is_admin = opt.check_admin()
    print("Losshound Network Optimizer")
    print("=" * 60)
    print(f"  Admin: {'Yes' if is_admin else 'No (some optimizations will be skipped)'}")
    print()

    if not is_admin:
        print("  TIP: Re-run as Administrator for full optimization.")
        print()

    print("Creating backup of current settings...")
    print("Running optimizations...\n")

    report = opt.optimize_all(skip_dns=skip_dns, skip_mtu=skip_mtu)

    _print_results(report.results)

    print()
    print(f"Summary: {report.summary}")
    print(f"Backup saved — run 'losshound restore' to undo.")


def _cmd_dns_benchmark(opt):
    """Benchmark DNS servers."""
    print("Losshound DNS Benchmark")
    print("=" * 60)
    print("Testing 14 public DNS servers...\n")

    results = opt.benchmark_dns()

    print(f"{'Rank':<5} {'Server':<18} {'Provider':<22} {'Avg ms':<10} {'Min ms':<10} {'Success':<8}")
    print("-" * 73)

    for i, r in enumerate(results):
        avg = f"{r.avg_ms:.1f}" if r.avg_ms != float("inf") else "N/A"
        mn = f"{r.min_ms:.1f}" if r.min_ms != float("inf") else "N/A"
        success = f"{r.success_rate * 100:.0f}%"

        marker = " "
        if i == 0:
            marker = "*"  # fastest

        print(f" {marker}{i+1:<4} {r.server:<18} {r.name:<22} {avg:<10} {mn:<10} {success:<8}")

    print()
    if results and results[0].success_rate > 0.5:
        print(f"  Fastest DNS: {results[0].name} ({results[0].server}) — {results[0].avg_ms:.1f}ms avg")
        print(f"  Run 'losshound optimize' to apply the fastest DNS automatically.")


def _cmd_status(opt):
    """Show current network optimization status."""
    print("Losshound Network Status")
    print("=" * 60)

    status = opt.get_optimization_status()

    is_admin = status.get("admin", False)
    print(f"  Admin privileges:     {'Yes' if is_admin else 'No'}")
    print()

    tcp = status.get("tcp", {})
    print("  TCP/IP Settings:")
    print(f"    Auto-tuning level:  {tcp.get('auto_tuning_level', 'unknown')}")
    print(f"    Congestion provider:{tcp.get('congestion_provider', 'unknown')}")
    print(f"    ECN capability:     {tcp.get('ecn_capability', 'unknown')}")
    print(f"    RSS:                {tcp.get('rss', 'unknown')}")
    print(f"    DCA:                {tcp.get('dca', 'unknown')}")
    print(f"    Timestamps:         {tcp.get('timestamps', 'unknown')}")
    print()

    print("  Network:")
    print(f"    DNS primary:        {status.get('dns_primary', 'auto') or 'auto'}")
    print(f"    DNS secondary:      {status.get('dns_secondary', '') or 'none'}")
    print(f"    MTU:                {status.get('mtu', 1500)}")

    throttling = status.get("network_throttling_index")
    if throttling is None:
        thr_text = "default (may be throttled)"
    elif throttling == 0xFFFFFFFF or throttling == -1:
        thr_text = "disabled (optimal)"
    else:
        thr_text = f"enabled ({throttling})"
    print(f"    Network throttling: {thr_text}")

    print(f"    Backup exists:      {'Yes' if status.get('backup_exists') else 'No'}")


def _cmd_restore(opt):
    """Restore settings from backup."""
    print("Losshound Restore")
    print("=" * 60)

    if not opt.check_admin():
        print("  WARNING: Running without admin — some settings cannot be restored.")
        print()

    print("Restoring from backup...\n")
    results = opt.restore_backup()

    if not results:
        print("  No backup found. Run 'losshound optimize' first.")
        return

    _print_results(results)

    succeeded = sum(1 for r in results if r.success)
    print(f"\nRestored {succeeded}/{len(results)} settings.")


def _print_results(results):
    """Print a table of optimization results."""
    print(f"  {'Optimization':<30} {'Status':<20} {'Before':<20} {'After':<20}")
    print(f"  {'-'*30} {'-'*20} {'-'*20} {'-'*20}")

    for r in results:
        if r.success:
            status = "Applied"
        elif r.needs_admin and r.error and "Administrator" in r.error:
            status = "Skipped (no admin)"
        else:
            status = f"Failed: {r.error or 'unknown'}"

        before = (r.before or "--")[:18]
        after = (r.after or "--")[:18]
        print(f"  {r.name:<30} {status:<20} {before:<20} {after:<20}")


def _cmd_benchmark(label: str, ping_count: int):
    """Run a full network performance benchmark."""
    from losshound.core.benchmark import (
        format_snapshot, run_benchmark, save_snapshot,
    )

    print("Losshound Network Benchmark")
    print("=" * 65)
    print(f"  Label: {label}")
    print(f"  Pings per target: {ping_count}")
    print()

    snapshot = run_benchmark(
        label=label,
        ping_count=ping_count,
        progress_callback=lambda msg: print(f"  {msg}"),
    )
    save_snapshot(snapshot)

    print()
    print(format_snapshot(snapshot))
    print()
    print(f"Benchmark saved as '{label}'.")

    if label == "before":
        print("  Now run 'losshound optimize' then 'losshound benchmark --label after'")
        print("  Finally run 'losshound compare' to see the difference!")
    elif label == "after":
        print("  Run 'losshound compare' to see before vs after!")


def _cmd_compare():
    """Compare before vs after benchmarks."""
    from losshound.core.benchmark import (
        compare_snapshots, format_comparison, get_latest_snapshot,
    )

    before = get_latest_snapshot("before")
    after = get_latest_snapshot("after")

    if not before:
        print("No 'before' benchmark found. Run: losshound benchmark --label before")
        return
    if not after:
        print("No 'after' benchmark found. Run: losshound benchmark --label after")
        return

    report = compare_snapshots(before, after)
    print()
    print(format_comparison(report))
    print()


def _cmd_load_benchmark(label: str):
    """Run a full network load benchmark."""
    from losshound.core.load_benchmark import (
        format_load_snapshot, run_load_benchmark, save_load_snapshot,
    )

    print("Losshound LOAD Benchmark")
    print("=" * 65)
    print(f"  Label: {label}")
    print(f"  Tests: idle latency, latency under load, bufferbloat,")
    print(f"         throughput, small packet responsiveness")
    print(f"  This will take ~60 seconds...")
    print()

    snapshot = run_load_benchmark(
        label=label,
        progress_callback=lambda msg: print(f"  {msg}"),
    )
    save_load_snapshot(snapshot)

    print()
    print(format_load_snapshot(snapshot))
    print()
    print(f"Load benchmark saved as '{label}'.")

    if label == "before":
        print("  Now run 'losshound optimize' then 'losshound load-benchmark --label after'")
        print("  Finally run 'losshound load-compare' to see the real difference!")
    elif label == "after":
        print("  Run 'losshound load-compare' to see before vs after!")


def _cmd_load_compare():
    """Compare before vs after load benchmarks."""
    from losshound.core.load_benchmark import (
        compare_load_snapshots, format_load_comparison, get_latest_load_snapshot,
    )

    before = get_latest_load_snapshot("before")
    after = get_latest_load_snapshot("after")

    if not before:
        print("No 'before' load benchmark found. Run: losshound load-benchmark --label before")
        return
    if not after:
        print("No 'after' load benchmark found. Run: losshound load-benchmark --label after")
        return

    report = compare_load_snapshots(before, after)
    print()
    print(format_load_comparison(report))
    print()
