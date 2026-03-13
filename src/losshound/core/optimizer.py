"""Network performance optimizer for Windows.

Provides DNS benchmarking, TCP/IP stack tuning, adapter optimisation,
MTU discovery, and various Windows network tweaks.  All changes can be
backed up before applying and restored later.

Most write operations require Administrator privileges.  When running
without elevation the optimizer will skip admin-only steps and record
them in the returned results so the caller can inform the user.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import subprocess
import time
import winreg
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from losshound.core.dns_bench import (
    DNS_SERVERS,
    DnsBenchmarkResult,
    benchmark_all as _dns_benchmark_all,
)

logger = logging.getLogger(__name__)

# Prevent console windows from flashing during subprocess calls.
_CREATE_NO_WINDOW: int = 0x08000000

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class OptimizeResult:
    """Outcome of a single optimisation action."""

    name: str
    success: bool
    before: str
    after: str
    needs_admin: bool
    error: Optional[str] = None


@dataclass
class TcpSettings:
    """Snapshot of TCP global parameters."""

    auto_tuning_level: str = "unknown"
    congestion_provider: str = "unknown"
    ecn_capability: str = "unknown"
    rss: str = "unknown"
    dca: str = "unknown"
    timestamps: str = "unknown"


@dataclass
class AdapterInfo:
    """Description of the active network adapter."""

    name: str
    interface_index: int
    ip_address: str
    mac_address: str
    speed: str


@dataclass
class AdapterBackup:
    """Snapshot of adapter-level settings."""

    name: str
    power_management_enabled: Optional[bool] = None
    interrupt_moderation_enabled: Optional[bool] = None


@dataclass
class BackupData:
    """Complete settings snapshot for later restoration."""

    timestamp: str
    tcp_settings: TcpSettings
    dns_servers: tuple[str, str]
    mtu: int
    network_throttling: Optional[int]
    nagle_disabled: bool
    nagle_interface_guid: Optional[str] = None
    adapter: Optional[AdapterBackup] = None


@dataclass
class OptimizeReport:
    """Aggregate report returned by :meth:`NetworkOptimizer.optimize_all`."""

    results: list[OptimizeResult]
    backup: BackupData
    admin: bool
    summary: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BACKUP_DIR = Path(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
) / "Losshound"
_BACKUP_FILE = _BACKUP_DIR / "optimizer_backup.json"


def _run(
    cmd: str | list[str],
    *,
    shell: bool = False,
    timeout: float = 30,
    english: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Execute a subprocess with common defaults.

    Parameters
    ----------
    cmd:
        Command to run.  If *shell* is ``True`` this should be a string,
        otherwise a list.
    shell:
        Whether to use shell execution.
    timeout:
        Maximum number of seconds to wait.
    english:
        If ``True``, prepend ``chcp 437 >nul &&`` (via cmd /c) so that
        the output is in English regardless of system locale.
    """
    if english:
        if isinstance(cmd, list):
            cmd = " ".join(cmd)
        cmd = f"chcp 437 >nul && {cmd}"
        args: str | list[str] = ["cmd", "/c", cmd]
        shell = False
    else:
        args = cmd

    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
        shell=shell,
    )


def _parse_netsh_table(output: str) -> dict[str, str]:
    """Parse ``key : value`` lines from netsh output into a dict."""
    result: dict[str, str] = {}
    for line in output.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key and value:
                result[key] = value
    return result


# ---------------------------------------------------------------------------
# NetworkOptimizer
# ---------------------------------------------------------------------------


class NetworkOptimizer:
    """Façade for all Windows network optimisation operations."""

    # ------------------------------------------------------------------
    # Admin check
    # ------------------------------------------------------------------

    @staticmethod
    def check_admin() -> bool:
        """Return ``True`` if the current process has Administrator rights."""
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except Exception:
            return False

    # ------------------------------------------------------------------
    # DNS benchmark & optimiser
    # ------------------------------------------------------------------

    def benchmark_dns(
        self, servers: list[str] | None = None
    ) -> list[DnsBenchmarkResult]:
        """Benchmark DNS servers and return results sorted fastest-first."""
        return _dns_benchmark_all(servers=servers)

    def get_current_dns(self) -> tuple[str, str]:
        """Return ``(primary, secondary)`` DNS servers for the active adapter.

        Falls back to ``("", "")`` if detection fails.
        """
        try:
            result = _run(
                "netsh interface ip show dnsservers", english=True,
            )
            servers: list[str] = re.findall(
                r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", result.stdout,
            )
            primary = servers[0] if len(servers) >= 1 else ""
            secondary = servers[1] if len(servers) >= 2 else ""
            return primary, secondary
        except Exception as exc:
            logger.warning("Failed to detect current DNS: %s", exc)
            return "", ""

    def apply_dns(self, primary: str, secondary: str) -> OptimizeResult:
        """Set DNS servers on the active network adapter (requires admin)."""
        name = "Set DNS servers"
        if not self.check_admin():
            return OptimizeResult(
                name=name, success=False,
                before="", after="",
                needs_admin=True,
                error="Administrator privileges required",
            )

        before_primary, before_secondary = self.get_current_dns()
        adapter = self._active_adapter_name()

        try:
            _run(
                f'netsh interface ip set dnsservers name="{adapter}" '
                f"static {primary} primary validate=no",
                english=True,
            )
            if secondary:
                _run(
                    f'netsh interface ip add dnsservers name="{adapter}" '
                    f"{secondary} index=2 validate=no",
                    english=True,
                )
            return OptimizeResult(
                name=name, success=True,
                before=f"{before_primary}, {before_secondary}",
                after=f"{primary}, {secondary}",
                needs_admin=True,
            )
        except Exception as exc:
            logger.error("Failed to set DNS: %s", exc)
            return OptimizeResult(
                name=name, success=False,
                before=f"{before_primary}, {before_secondary}",
                after="",
                needs_admin=True,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # TCP/IP stack
    # ------------------------------------------------------------------

    def get_tcp_settings(self) -> TcpSettings:
        """Read current TCP global parameters via ``netsh``."""
        settings = TcpSettings()
        try:
            result = _run(
                "netsh interface tcp show global", english=True,
            )
            table = _parse_netsh_table(result.stdout)

            settings.auto_tuning_level = table.get(
                "receive window auto-tuning level", "unknown",
            )
            settings.congestion_provider = table.get(
                "add-on congestion control provider", table.get(
                    "supplemental congestion control provider", "unknown",
                ),
            )
            settings.ecn_capability = table.get("ecn capability", "unknown")
            settings.rss = table.get(
                "receive-side scaling state", "unknown",
            )
            settings.dca = table.get(
                "direct cache access (dca)", "unknown",
            )
            settings.timestamps = table.get("timestamps", "unknown")
        except Exception as exc:
            logger.warning("Failed to read TCP settings: %s", exc)
        return settings

    def optimize_tcp(self) -> list[OptimizeResult]:
        """Apply optimal TCP/IP stack settings.  Returns one result per tweak."""
        results: list[OptimizeResult] = []
        if not self.check_admin():
            for label in (
                "TCP auto-tuning", "Congestion provider",
                "ECN capability", "RSS", "DCA", "TCP timestamps",
            ):
                results.append(OptimizeResult(
                    name=label, success=False, before="", after="",
                    needs_admin=True,
                    error="Administrator privileges required",
                ))
            return results

        current = self.get_tcp_settings()
        tweaks: list[tuple[str, str, str, str]] = [
            (
                "TCP auto-tuning",
                "netsh int tcp set global autotuninglevel=normal",
                current.auto_tuning_level,
                "normal",
            ),
            (
                "Congestion provider",
                "netsh int tcp set supplemental template=Internet "
                "congestionprovider=ctcp",
                current.congestion_provider,
                "ctcp",
            ),
            (
                "ECN capability",
                "netsh int tcp set global ecncapability=enabled",
                current.ecn_capability,
                "enabled",
            ),
            (
                "RSS",
                "netsh int tcp set global rss=enabled",
                current.rss,
                "enabled",
            ),
            (
                "DCA",
                "netsh int tcp set global dca=enabled",
                current.dca,
                "enabled",
            ),
            (
                "TCP timestamps",
                "netsh int tcp set global timestamps=enabled",
                current.timestamps,
                "enabled",
            ),
        ]

        for label, command, before, desired in tweaks:
            try:
                proc = _run(command, english=True)
                ok = proc.returncode == 0
                error = proc.stderr.strip() if not ok else None
                # Some commands succeed with non-zero return codes but write
                # to stdout; treat empty stderr as success.
                if not ok and not error:
                    ok = True
                    error = None
                results.append(OptimizeResult(
                    name=label, success=ok,
                    before=before, after=desired,
                    needs_admin=True, error=error,
                ))
            except Exception as exc:
                logger.error("TCP tweak '%s' failed: %s", label, exc)
                results.append(OptimizeResult(
                    name=label, success=False,
                    before=before, after=desired,
                    needs_admin=True, error=str(exc),
                ))

        return results

    # ------------------------------------------------------------------
    # Network adapter
    # ------------------------------------------------------------------

    def get_active_adapter(self) -> AdapterInfo:
        """Detect the active network adapter via PowerShell."""
        try:
            result = _run(
                [
                    "powershell", "-NoProfile", "-Command",
                    (
                        "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} "
                        "| Select-Object -First 1 Name, InterfaceIndex, "
                        "MacAddress, LinkSpeed "
                        "| ConvertTo-Json"
                    ),
                ],
            )
            data = json.loads(result.stdout)
            # Fetch IP address separately
            ip_result = _run(
                [
                    "powershell", "-NoProfile", "-Command",
                    (
                        f"(Get-NetIPAddress -InterfaceIndex {data['InterfaceIndex']} "
                        "-AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress"
                    ),
                ],
            )
            ip_addr = ip_result.stdout.strip().splitlines()[0] if ip_result.stdout.strip() else ""
            return AdapterInfo(
                name=data.get("Name", ""),
                interface_index=int(data.get("InterfaceIndex", 0)),
                ip_address=ip_addr,
                mac_address=data.get("MacAddress", ""),
                speed=data.get("LinkSpeed", ""),
            )
        except Exception as exc:
            logger.warning("Failed to detect active adapter: %s", exc)
            # Fallback: try ipconfig parsing
            return AdapterInfo(
                name=self._active_adapter_name(),
                interface_index=0,
                ip_address="",
                mac_address="",
                speed="",
            )

    def _active_adapter_name(self) -> str:
        """Best-effort adapter name detection for use in netsh commands."""
        try:
            result = _run(
                [
                    "powershell", "-NoProfile", "-Command",
                    "(Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} "
                    "| Select-Object -First 1).Name",
                ],
            )
            name = result.stdout.strip()
            if name:
                return name
        except Exception:
            pass

        # Fallback: parse netsh
        try:
            result = _run(
                "netsh interface show interface", english=True,
            )
            for line in result.stdout.splitlines():
                if "Connected" in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        return " ".join(parts[3:])
        except Exception:
            pass
        return "Ethernet"

    def optimize_adapter(self) -> list[OptimizeResult]:
        """Optimise the active network adapter settings."""
        results: list[OptimizeResult] = []
        if not self.check_admin():
            results.append(OptimizeResult(
                name="Adapter power management",
                success=False, before="", after="",
                needs_admin=True,
                error="Administrator privileges required",
            ))
            return results

        adapter = self.get_active_adapter()

        # Disable power management (allow the computer to turn off this
        # device to save power).
        try:
            proc = _run(
                [
                    "powershell", "-NoProfile", "-Command",
                    (
                        f"Disable-NetAdapterPowerManagement "
                        f"-Name '{adapter.name}' "
                        f"-ErrorAction SilentlyContinue"
                    ),
                ],
            )
            results.append(OptimizeResult(
                name="Adapter power management",
                success=proc.returncode == 0,
                before="enabled", after="disabled",
                needs_admin=True,
                error=proc.stderr.strip() or None if proc.returncode != 0 else None,
            ))
        except Exception as exc:
            results.append(OptimizeResult(
                name="Adapter power management",
                success=False, before="enabled", after="disabled",
                needs_admin=True, error=str(exc),
            ))

        # Interrupt moderation — disable for lowest latency
        try:
            proc = _run(
                [
                    "powershell", "-NoProfile", "-Command",
                    (
                        f"Set-NetAdapterAdvancedProperty "
                        f"-Name '{adapter.name}' "
                        f"-RegistryKeyword '*InterruptModeration' "
                        f"-RegistryValue 0 "
                        f"-ErrorAction SilentlyContinue"
                    ),
                ],
            )
            results.append(OptimizeResult(
                name="Interrupt moderation",
                success=proc.returncode == 0,
                before="enabled", after="disabled",
                needs_admin=True,
                error=proc.stderr.strip() or None if proc.returncode != 0 else None,
            ))
        except Exception as exc:
            results.append(OptimizeResult(
                name="Interrupt moderation",
                success=False, before="enabled", after="disabled",
                needs_admin=True, error=str(exc),
            ))

        return results

    # ------------------------------------------------------------------
    # Windows network tweaks
    # ------------------------------------------------------------------

    def flush_dns_cache(self) -> OptimizeResult:
        """Flush the Windows DNS resolver cache."""
        try:
            proc = _run("ipconfig /flushdns", english=True)
            ok = "successfully" in proc.stdout.lower() or proc.returncode == 0
            return OptimizeResult(
                name="Flush DNS cache", success=ok,
                before="cached", after="flushed",
                needs_admin=False,
                error=proc.stderr.strip() or None if not ok else None,
            )
        except Exception as exc:
            return OptimizeResult(
                name="Flush DNS cache", success=False,
                before="cached", after="flushed",
                needs_admin=False, error=str(exc),
            )

    def flush_arp_cache(self) -> OptimizeResult:
        """Flush the ARP cache (requires admin)."""
        name = "Flush ARP cache"
        if not self.check_admin():
            return OptimizeResult(
                name=name, success=False, before="", after="",
                needs_admin=True,
                error="Administrator privileges required",
            )
        try:
            proc = _run(
                "netsh interface ip delete arpcache", english=True,
            )
            return OptimizeResult(
                name=name, success=proc.returncode == 0,
                before="cached", after="flushed",
                needs_admin=True,
                error=proc.stderr.strip() or None if proc.returncode != 0 else None,
            )
        except Exception as exc:
            return OptimizeResult(
                name=name, success=False,
                before="cached", after="flushed",
                needs_admin=True, error=str(exc),
            )

    def get_network_throttling_index(self) -> int | None:
        """Read the ``NetworkThrottlingIndex`` value from the registry."""
        key_path = (
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia"
            r"\SystemProfile"
        )
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "NetworkThrottlingIndex")
                return int(value)
        except OSError:
            return None

    def disable_network_throttling(self) -> OptimizeResult:
        """Set ``NetworkThrottlingIndex`` to ``0xFFFFFFFF`` (requires admin)."""
        name = "Disable network throttling"
        if not self.check_admin():
            return OptimizeResult(
                name=name, success=False, before="", after="",
                needs_admin=True,
                error="Administrator privileges required",
            )

        key_path = (
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia"
            r"\SystemProfile"
        )
        before_val = self.get_network_throttling_index()
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, key_path, 0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(
                    key, "NetworkThrottlingIndex", 0,
                    winreg.REG_DWORD, 0xFFFFFFFF,
                )
            return OptimizeResult(
                name=name, success=True,
                before=str(before_val) if before_val is not None else "default",
                after="0xFFFFFFFF (disabled)",
                needs_admin=True,
            )
        except OSError as exc:
            return OptimizeResult(
                name=name, success=False,
                before=str(before_val) if before_val is not None else "default",
                after="",
                needs_admin=True, error=str(exc),
            )

    def optimize_nagle(self) -> OptimizeResult:
        """Disable Nagle's algorithm for the active adapter (requires admin).

        Sets ``TcpAckFrequency`` and ``TCPNoDelay`` to ``1`` in the
        registry for the interface that owns the current default gateway.
        """
        name = "Disable Nagle's algorithm"
        if not self.check_admin():
            return OptimizeResult(
                name=name, success=False, before="", after="",
                needs_admin=True,
                error="Administrator privileges required",
            )

        base_path = (
            r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
        )
        try:
            # Find the sub-key whose DhcpDefaultGateway or DefaultGateway is
            # non-empty — that's the active interface.
            target_guid: str | None = None
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path) as base:
                idx = 0
                while True:
                    try:
                        guid = winreg.EnumKey(base, idx)
                    except OSError:
                        break
                    idx += 1
                    try:
                        with winreg.OpenKey(base, guid) as sub:
                            for val_name in (
                                "DhcpDefaultGateway", "DefaultGateway",
                            ):
                                try:
                                    gw, _ = winreg.QueryValueEx(sub, val_name)
                                    if gw and any(g for g in gw if g):
                                        target_guid = guid
                                        break
                                except OSError:
                                    continue
                    except OSError:
                        continue
                    if target_guid:
                        break

            if not target_guid:
                return OptimizeResult(
                    name=name, success=False,
                    before="", after="",
                    needs_admin=True,
                    error="Could not identify active network interface in registry",
                )

            iface_path = f"{base_path}\\{target_guid}"
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, iface_path, 0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(
                    key, "TcpAckFrequency", 0, winreg.REG_DWORD, 1,
                )
                winreg.SetValueEx(
                    key, "TCPNoDelay", 0, winreg.REG_DWORD, 1,
                )

            return OptimizeResult(
                name=name, success=True,
                before="enabled (default)",
                after="disabled (TcpAckFrequency=1, TCPNoDelay=1)",
                needs_admin=True,
            )
        except OSError as exc:
            return OptimizeResult(
                name=name, success=False,
                before="", after="",
                needs_admin=True, error=str(exc),
            )

    # ------------------------------------------------------------------
    # MTU optimiser
    # ------------------------------------------------------------------

    def get_current_mtu(self) -> int:
        """Read the current MTU for the active adapter."""
        try:
            adapter = self._active_adapter_name()
            result = _run(
                f'netsh interface ipv4 show subinterfaces', english=True,
            )
            for line in result.stdout.splitlines():
                if adapter.lower() in line.lower():
                    parts = line.split()
                    for part in parts:
                        if part.isdigit():
                            mtu = int(part)
                            if 500 <= mtu <= 9000:
                                return mtu
        except Exception as exc:
            logger.warning("Failed to read MTU: %s", exc)
        return 1500  # sensible default

    def find_optimal_mtu(self, target: str = "8.8.8.8") -> int:
        """Binary-search for the largest MTU that does not cause fragmentation.

        Uses ``ping -f -l <size>`` to test.  The returned value includes
        the 28-byte IP+ICMP header overhead.
        """
        low = 500
        high = 1500
        best = 1400  # safe fallback

        while low <= high:
            mid = (low + high) // 2
            # ``ping -f -l`` sends a payload of *mid* bytes.
            # The actual MTU = payload + 28 (20 IP + 8 ICMP header).
            try:
                proc = _run(
                    f"chcp 437 >nul && ping -n 1 -f -l {mid} -w 2000 {target}",
                    english=False,  # already included chcp in command
                )
                stdout = proc.stdout
            except Exception:
                break

            # If the reply contains "fragmented" or "DF set" it means the
            # packet was too large.
            needs_frag = (
                "must be fragmented" in stdout.lower()
                or "packet needs to be fragmented" in stdout.lower()
                or "df set" in stdout.lower()
            )

            if needs_frag:
                high = mid - 1
            else:
                # Check for a successful reply
                if "reply from" in stdout.lower() or "ttl=" in stdout.lower():
                    best = mid
                    low = mid + 1
                else:
                    # Timeout or other failure — shrink
                    high = mid - 1

        optimal_mtu = best + 28  # add IP+ICMP header
        logger.info("Optimal MTU detected: %d (payload %d + 28)", optimal_mtu, best)
        return optimal_mtu

    def apply_mtu(self, mtu: int) -> OptimizeResult:
        """Set the MTU on the active adapter (requires admin)."""
        name = "Set MTU"
        if not self.check_admin():
            return OptimizeResult(
                name=name, success=False,
                before="", after="",
                needs_admin=True,
                error="Administrator privileges required",
            )

        before_mtu = self.get_current_mtu()
        adapter = self._active_adapter_name()
        try:
            proc = _run(
                f'netsh interface ipv4 set subinterface "{adapter}" '
                f"mtu={mtu} store=persistent",
                english=True,
            )
            ok = proc.returncode == 0 or "ok" in proc.stdout.lower()
            return OptimizeResult(
                name=name, success=ok,
                before=str(before_mtu), after=str(mtu),
                needs_admin=True,
                error=proc.stderr.strip() or None if not ok else None,
            )
        except Exception as exc:
            return OptimizeResult(
                name=name, success=False,
                before=str(before_mtu), after=str(mtu),
                needs_admin=True, error=str(exc),
            )

    # ------------------------------------------------------------------
    # Backup & restore
    # ------------------------------------------------------------------

    def create_backup(self) -> BackupData:
        """Snapshot all current settings so they can be restored later."""
        tcp = self.get_tcp_settings()
        dns = self.get_current_dns()
        mtu = self.get_current_mtu()
        throttling = self.get_network_throttling_index()

        # Check Nagle state and record the interface GUID
        nagle_disabled = False
        nagle_guid: str | None = None
        base_path = (
            r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
        )
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path) as base:
                idx = 0
                while True:
                    try:
                        guid = winreg.EnumKey(base, idx)
                    except OSError:
                        break
                    idx += 1
                    try:
                        with winreg.OpenKey(base, guid) as sub:
                            for val_name in (
                                "DhcpDefaultGateway", "DefaultGateway",
                            ):
                                try:
                                    gw, _ = winreg.QueryValueEx(sub, val_name)
                                    if gw and any(g for g in gw if g):
                                        nagle_guid = guid
                                        try:
                                            nd, _ = winreg.QueryValueEx(
                                                sub, "TCPNoDelay",
                                            )
                                            nagle_disabled = nd == 1
                                        except OSError:
                                            pass
                                        break
                                except OSError:
                                    continue
                    except OSError:
                        continue
                    if nagle_guid:
                        break
        except OSError:
            pass

        # Snapshot adapter settings
        adapter_backup = self._backup_adapter_settings()

        backup = BackupData(
            timestamp=datetime.now(timezone.utc).isoformat(),
            tcp_settings=tcp,
            dns_servers=dns,
            mtu=mtu,
            network_throttling=throttling,
            nagle_disabled=nagle_disabled,
            nagle_interface_guid=nagle_guid,
            adapter=adapter_backup,
        )

        # Persist to disk
        self._save_backup(backup)
        logger.info("Created settings backup at %s", _BACKUP_FILE)
        return backup

    def _backup_adapter_settings(self) -> AdapterBackup | None:
        """Snapshot current adapter power management and interrupt moderation."""
        try:
            adapter = self.get_active_adapter()
            name = adapter.name
            if not name:
                return None

            # Power management state
            power_enabled: bool | None = None
            try:
                proc = _run([
                    "powershell", "-NoProfile", "-Command",
                    f"(Get-NetAdapterPowerManagement -Name '{name}' "
                    f"-ErrorAction SilentlyContinue).AllowComputerToTurnOffDevice",
                ])
                val = proc.stdout.strip().lower()
                if val in ("enabled", "true"):
                    power_enabled = True
                elif val in ("disabled", "false", "unsupported"):
                    power_enabled = False
            except Exception:
                pass

            # Interrupt moderation state
            int_mod_enabled: bool | None = None
            try:
                proc = _run([
                    "powershell", "-NoProfile", "-Command",
                    f"(Get-NetAdapterAdvancedProperty -Name '{name}' "
                    f"-RegistryKeyword '*InterruptModeration' "
                    f"-ErrorAction SilentlyContinue).RegistryValue",
                ])
                val = proc.stdout.strip()
                if val == "1":
                    int_mod_enabled = True
                elif val == "0":
                    int_mod_enabled = False
            except Exception:
                pass

            return AdapterBackup(
                name=name,
                power_management_enabled=power_enabled,
                interrupt_moderation_enabled=int_mod_enabled,
            )
        except Exception as exc:
            logger.warning("Failed to backup adapter settings: %s", exc)
            return None

    @staticmethod
    def _save_backup(backup: BackupData) -> None:
        _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(backup)
        # tuple -> list for JSON, will be restored on load
        data["dns_servers"] = list(data["dns_servers"])
        with open(_BACKUP_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    @staticmethod
    def _load_backup() -> BackupData | None:
        if not _BACKUP_FILE.is_file():
            return None
        try:
            with open(_BACKUP_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            tcp = TcpSettings(**data.pop("tcp_settings"))
            data["tcp_settings"] = tcp
            data["dns_servers"] = tuple(data["dns_servers"])
            # Handle adapter sub-object
            adapter_raw = data.pop("adapter", None)
            if adapter_raw and isinstance(adapter_raw, dict):
                data["adapter"] = AdapterBackup(**adapter_raw)
            else:
                data["adapter"] = None
            return BackupData(**data)
        except Exception as exc:
            logger.warning("Failed to load backup: %s", exc)
            return None

    def restore_backup(self, backup: BackupData | None = None) -> list[OptimizeResult]:
        """Restore **all** settings from a backup.

        If *backup* is ``None`` the most recent on-disk backup is used.
        Every setting that was changed by :meth:`optimize_all` is reverted:
        DNS, MTU, all TCP globals, network throttling, Nagle's algorithm,
        adapter power management, and interrupt moderation.
        """
        results: list[OptimizeResult] = []

        if backup is None:
            backup = self._load_backup()
        if backup is None:
            results.append(OptimizeResult(
                name="Restore backup", success=False,
                before="", after="",
                needs_admin=False,
                error="No backup found",
            ))
            return results

        is_admin = self.check_admin()

        def _need_admin(name: str) -> OptimizeResult:
            return OptimizeResult(
                name=name, success=False, before="", after="",
                needs_admin=True,
                error="Administrator privileges required",
            )

        # --- DNS ---
        if backup.dns_servers[0]:
            if is_admin:
                results.append(
                    self.apply_dns(backup.dns_servers[0], backup.dns_servers[1]),
                )
            else:
                results.append(_need_admin("Restore DNS"))

        # --- MTU ---
        if is_admin:
            results.append(self.apply_mtu(backup.mtu))
        else:
            results.append(_need_admin("Restore MTU"))

        # --- All TCP global settings ---
        tcp_tweaks: list[tuple[str, str, str]] = [
            (
                "Restore TCP auto-tuning",
                "netsh int tcp set global autotuninglevel={}",
                backup.tcp_settings.auto_tuning_level,
            ),
            (
                "Restore congestion provider",
                "netsh int tcp set supplemental template=Internet congestionprovider={}",
                backup.tcp_settings.congestion_provider,
            ),
            (
                "Restore ECN",
                "netsh int tcp set global ecncapability={}",
                backup.tcp_settings.ecn_capability,
            ),
            (
                "Restore RSS",
                "netsh int tcp set global rss={}",
                backup.tcp_settings.rss,
            ),
            (
                "Restore DCA",
                "netsh int tcp set global dca={}",
                backup.tcp_settings.dca,
            ),
            (
                "Restore TCP timestamps",
                "netsh int tcp set global timestamps={}",
                backup.tcp_settings.timestamps,
            ),
        ]

        for label, cmd_template, value in tcp_tweaks:
            if not value or value == "unknown":
                continue
            if not is_admin:
                results.append(_need_admin(label))
                continue
            try:
                proc = _run(cmd_template.format(value), english=True)
                ok = proc.returncode == 0
                error = proc.stderr.strip() if not ok else None
                if not ok and not error:
                    ok = True
                    error = None
                results.append(OptimizeResult(
                    name=label, success=ok,
                    before="current", after=value,
                    needs_admin=True, error=error,
                ))
            except Exception as exc:
                results.append(OptimizeResult(
                    name=label, success=False,
                    before="current", after=value,
                    needs_admin=True, error=str(exc),
                ))

        # --- Network throttling ---
        if backup.network_throttling is not None:
            if not is_admin:
                results.append(_need_admin("Restore network throttling"))
            else:
                key_path = (
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia"
                    r"\SystemProfile"
                )
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE, key_path, 0,
                        winreg.KEY_SET_VALUE,
                    ) as key:
                        winreg.SetValueEx(
                            key, "NetworkThrottlingIndex", 0,
                            winreg.REG_DWORD, backup.network_throttling,
                        )
                    results.append(OptimizeResult(
                        name="Restore network throttling", success=True,
                        before="current", after=str(backup.network_throttling),
                        needs_admin=True,
                    ))
                except OSError as exc:
                    results.append(OptimizeResult(
                        name="Restore network throttling", success=False,
                        before="current", after=str(backup.network_throttling),
                        needs_admin=True, error=str(exc),
                    ))

        # --- Nagle's algorithm ---
        if backup.nagle_interface_guid and not backup.nagle_disabled:
            # Nagle was enabled before — remove the registry overrides
            if not is_admin:
                results.append(_need_admin("Restore Nagle's algorithm"))
            else:
                iface_path = (
                    r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
                    r"\Interfaces\\" + backup.nagle_interface_guid
                )
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE, iface_path, 0,
                        winreg.KEY_SET_VALUE,
                    ) as key:
                        # Delete overrides to return to default (Nagle enabled)
                        for val_name in ("TcpAckFrequency", "TCPNoDelay"):
                            try:
                                winreg.DeleteValue(key, val_name)
                            except OSError:
                                pass
                    results.append(OptimizeResult(
                        name="Restore Nagle's algorithm", success=True,
                        before="disabled", after="enabled (default)",
                        needs_admin=True,
                    ))
                except OSError as exc:
                    results.append(OptimizeResult(
                        name="Restore Nagle's algorithm", success=False,
                        before="disabled", after="enabled",
                        needs_admin=True, error=str(exc),
                    ))

        # --- Adapter power management ---
        if backup.adapter and backup.adapter.name:
            adapter_name = backup.adapter.name

            if backup.adapter.power_management_enabled is True:
                if not is_admin:
                    results.append(_need_admin("Restore adapter power management"))
                else:
                    try:
                        proc = _run([
                            "powershell", "-NoProfile", "-Command",
                            f"Enable-NetAdapterPowerManagement "
                            f"-Name '{adapter_name}' "
                            f"-ErrorAction SilentlyContinue",
                        ])
                        results.append(OptimizeResult(
                            name="Restore adapter power management",
                            success=proc.returncode == 0,
                            before="disabled", after="enabled",
                            needs_admin=True,
                            error=proc.stderr.strip() or None if proc.returncode != 0 else None,
                        ))
                    except Exception as exc:
                        results.append(OptimizeResult(
                            name="Restore adapter power management",
                            success=False,
                            before="disabled", after="enabled",
                            needs_admin=True, error=str(exc),
                        ))

            if backup.adapter.interrupt_moderation_enabled is True:
                if not is_admin:
                    results.append(_need_admin("Restore interrupt moderation"))
                else:
                    try:
                        proc = _run([
                            "powershell", "-NoProfile", "-Command",
                            f"Set-NetAdapterAdvancedProperty "
                            f"-Name '{adapter_name}' "
                            f"-RegistryKeyword '*InterruptModeration' "
                            f"-RegistryValue 1 "
                            f"-ErrorAction SilentlyContinue",
                        ])
                        results.append(OptimizeResult(
                            name="Restore interrupt moderation",
                            success=proc.returncode == 0,
                            before="disabled", after="enabled",
                            needs_admin=True,
                            error=proc.stderr.strip() or None if proc.returncode != 0 else None,
                        ))
                    except Exception as exc:
                        results.append(OptimizeResult(
                            name="Restore interrupt moderation",
                            success=False,
                            before="disabled", after="enabled",
                            needs_admin=True, error=str(exc),
                        ))

        return results

    # ------------------------------------------------------------------
    # Status check
    # ------------------------------------------------------------------

    def get_optimization_status(self) -> dict:
        """Return the current state of all optimisable settings."""
        tcp = self.get_tcp_settings()
        dns = self.get_current_dns()
        mtu = self.get_current_mtu()
        throttling = self.get_network_throttling_index()

        return {
            "admin": self.check_admin(),
            "tcp": asdict(tcp),
            "dns_primary": dns[0],
            "dns_secondary": dns[1],
            "mtu": mtu,
            "network_throttling_index": throttling,
            "backup_exists": _BACKUP_FILE.is_file(),
        }

    # ------------------------------------------------------------------
    # Full optimise
    # ------------------------------------------------------------------

    def optimize_all(
        self,
        *,
        skip_dns: bool = False,
        skip_mtu: bool = False,
    ) -> OptimizeReport:
        """Run all optimisations and return a comprehensive report.

        A backup of the current settings is created first.

        Parameters
        ----------
        skip_dns:
            If ``True``, do not benchmark or change DNS servers.
        skip_mtu:
            If ``True``, do not discover or change MTU.
        """
        is_admin = self.check_admin()
        results: list[OptimizeResult] = []

        # --- Backup ---
        backup = self.create_backup()

        # --- DNS ---
        if not skip_dns:
            logger.info("Running DNS benchmark ...")
            dns_results = self.benchmark_dns()
            if dns_results and dns_results[0].success_rate > 0.5:
                best = dns_results[0]
                # Pick a secondary from a different provider
                secondary = ""
                for r in dns_results[1:]:
                    if r.name != best.name and r.success_rate > 0.5:
                        secondary = r.server
                        break
                results.append(self.apply_dns(best.server, secondary))
            else:
                results.append(OptimizeResult(
                    name="DNS optimization",
                    success=False,
                    before="", after="",
                    needs_admin=False,
                    error="No reliable DNS servers found during benchmark",
                ))

        # --- TCP ---
        results.extend(self.optimize_tcp())

        # --- Adapter ---
        results.extend(self.optimize_adapter())

        # --- Flush caches ---
        results.append(self.flush_dns_cache())
        results.append(self.flush_arp_cache())

        # --- Network throttling ---
        results.append(self.disable_network_throttling())

        # --- Nagle ---
        results.append(self.optimize_nagle())

        # --- MTU ---
        if not skip_mtu:
            logger.info("Discovering optimal MTU ...")
            optimal_mtu = self.find_optimal_mtu()
            results.append(self.apply_mtu(optimal_mtu))

        # --- Summary ---
        total = len(results)
        succeeded = sum(1 for r in results if r.success)
        skipped_admin = sum(
            1 for r in results if not r.success and r.needs_admin and not is_admin
        )
        failed = total - succeeded - skipped_admin

        parts: list[str] = [f"{succeeded}/{total} optimisations applied."]
        if skipped_admin:
            parts.append(
                f"{skipped_admin} skipped (requires Administrator).",
            )
        if failed:
            parts.append(f"{failed} failed.")
        summary = " ".join(parts)

        logger.info("Optimisation complete: %s", summary)

        return OptimizeReport(
            results=results,
            backup=backup,
            admin=is_admin,
            summary=summary,
        )
