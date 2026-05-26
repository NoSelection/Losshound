from __future__ import annotations

import logging
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# Basic OUI dictionary for popular manufacturers
_OUI_DB = {
    "00-00-0C": "Cisco",
    "00-03-93": "Apple",
    "00-05-5D": "D-Link",
    "00-0D-3A": "Microsoft",
    "00-14-22": "Dell",
    "00-1C-42": "Parallels",
    "00-1D-0F": "TP-Link",
    "00-21-70": "Dell",
    "00-25-90": "Supermicro",
    "00-26-82": "Apple",
    "00-50-56": "VMware",
    "00-90-7F": "WatchGuard",
    "00-A0-C9": "Intel",
    "00-C0-CA": "Alfa Network",
    "00-E0-4C": "Realtek",
    "04-18-0F": "Huawei",
    "04-D9-F5": "ASUSTek",
    "08-00-27": "VirtualBox",
    "0C-80-63": "Apple",
    "10-DD-B1": "Apple",
    "14-7D-DA": "Xiaomi",
    "1C-3B-F3": "HP",
    "24-A0-74": "Apple",
    "2C-F0-A2": "Samsung",
    "3C-5C-C4": "Intel",
    "3C-D9-2B": "HP",
    "40-8D-5C": "Apple",
    "48-2C-6A": "HTC",
    "50-3E-AA": "Samsung",
    "54-E4-3A": "Apple",
    "58-E8-76": "Xiaomi",
    "60-03-08": "Apple",
    "64-09-80": "Apple",
    "70-85-C2": "Intel",
    "70-EF-25": "Intel",
    "7C-D3-0A": "Apple",
    "80-E6-50": "Apple",
    "8C-85-90": "Apple",
    "90-DD-5D": "VMware",
    "9C-B6-54": "Xiaomi",
    "A4-77-33": "Samsung",
    "A4-83-E7": "Apple",
    "B0-C9-43": "Samsung",
    "B4-8B-19": "Intel",
    "B8-27-EB": "Raspberry Pi",
    "B8-E9-37": "Sonos",
    "C4-93-D9": "Samsung",
    "D0-50-99": "ASUSTek",
    "D8-D3-85": "HP",
    "D8-FC-93": "Apple",
    "E0-D5-5E": "Intel",
    "E4-E0-A6": "Huawei",
    "E8-94-F6": "TP-Link",
    "F0-18-98": "Apple",
    "F0-2F-A7": "Samsung",
    "F4-0F-24": "Apple",
    "F4-37-B7": "Intel",
    "F8-E9-03": "Intel",
    "FC-AA-14": "Samsung",
}


def run_command_resilient(args: List[str]) -> str:
    """Run a subprocess command and decode its output using CP850 fallback to avoid crashes."""
    try:
        res = subprocess.run(
            args,
            capture_output=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        # Try cp850 (standard OEM codepage on Western Windows) then utf-8, ignoring decoding errors
        try:
            return res.stdout.decode("cp850", errors="ignore")
        except Exception:
            return res.stdout.decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.warning("Failed running command %s: %s", args, exc)
        return ""


def get_local_network_info() -> Dict[str, str]:
    """Parse ipconfig to get local IPv4 address and subnet mask."""
    output = run_command_resilient(["ipconfig"])
    
    # We look for sections containing "IPv4 Address" and "Subnet Mask"
    ip_pattern = re.compile(r"IPv4 Address.*?:\s*([\d\.]+)")
    mask_pattern = re.compile(r"Subnet Mask.*?:\s*([\d\.]+)")
    
    ips = ip_pattern.findall(output)
    masks = mask_pattern.findall(output)
    
    result = {"ip": "", "mask": ""}
    for ip, mask in zip(ips, masks):
        # Skip APIPA (Automatic Private IP Addressing) address range
        if ip != "0.0.0.0" and not ip.startswith("169.254."):
            result["ip"] = ip
            result["mask"] = mask
            break
            
    return result


def get_subnet_ips(local_ip: str) -> List[str]:
    """Given a local IP, return the list of all host IPs in the /24 subnet."""
    if not local_ip:
        return []
    parts = local_ip.split(".")
    if len(parts) == 4:
        prefix = ".".join(parts[:3])
        return [f"{prefix}.{i}" for i in range(1, 255) if f"{prefix}.{i}" != local_ip]
    return []


def ping_ip(ip: str) -> None:
    """Send a single low-timeout ping to trigger ARP tables."""
    try:
        subprocess.run(
            ["ping", "-n", "1", "-w", "150", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass


def run_ping_sweep(ips: List[str]) -> None:
    """Ping all subnet IPs concurrently to populate the system's ARP cache."""
    with ThreadPoolExecutor(max_workers=32) as executor:
        executor.map(ping_ip, ips)


def lookup_vendor(mac: str) -> str:
    """Resolve vendor name using local OUI dictionary with online API fallback."""
    clean_mac = mac.replace(":", "-").upper()
    prefix = clean_mac[:8]
    local_val = _OUI_DB.get(prefix)
    if local_val:
        return local_val
        
    # Online API fallback
    import urllib.request
    import urllib.parse
    url = f"https://api.macvendors.com/{urllib.parse.quote(clean_mac)}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Losshound/0.1"}
        )
        with urllib.request.urlopen(req, timeout=1.5) as response:
            vendor = response.read().decode("utf-8").strip()
            if vendor:
                return vendor
    except Exception as exc:
        logger.debug("OUI API lookup failed for %s: %s", mac, exc)
        
    return "Unknown"


def resolve_netbios_name(ip: str) -> str:
    """Attempt to resolve hostname of an IP via a UDP NetBIOS Node Status query on port 137."""
    query = (
        b"\x85\x7e"  # Transaction ID
        b"\x00\x00"  # Flags
        b"\x00\x01"  # Questions
        b"\x00\x00"  # Answer RRs
        b"\x00\x00"  # Authority RRs
        b"\x00\x00"  # Additional RRs
        b"\x20"      # Name length (32)
        b"CKAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # "*" padded wildcard representation
        b"\x00"      # Name terminator
        b"\x00\x21"  # Type: NBSTAT
        b"\x00\x01"  # Class: IN
    )
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.4)
        sock.sendto(query, (ip, 137))
        data, _ = sock.recvfrom(1024)
        
        if len(data) < 57:
            return ""
            
        num_names = data[56]
        offset = 57
        for _ in range(num_names):
            if offset + 18 > len(data):
                break
            name = data[offset:offset+15].strip().decode("ascii", errors="ignore")
            name_type = data[offset+15]
            if name_type == 0x00:  # Workstation name
                return name.strip()
            offset += 18
    except Exception:
        pass
    finally:
        if sock:
            sock.close()
    return ""


def resolve_hostname_safe(ip: str) -> str:
    """Resolve IP to hostname using socket DNS then NetBIOS fallback."""
    original_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(1.0)
        hostname, _, _ = socket.gethostbyaddr(ip)
        if hostname:
            return hostname
    except Exception:
        pass
    finally:
        socket.setdefaulttimeout(original_timeout)
        
    # NetBIOS fallback
    nb_name = resolve_netbios_name(ip)
    if nb_name:
        return nb_name
        
    return ""


def parse_arp_table(local_ip: str) -> List[Dict[str, str]]:
    """Parse the system's ARP table to find connected devices, ignoring broadcast/multicast."""
    output = run_command_resilient(["arp", "-a"])
    
    # Matches dynamic or static entry: IP physical-address type
    # e.g., 192.168.1.1           1c-3b-f3-ea-bb-cc     dynamic
    pattern = re.compile(
        r"^\s*([\d\.]+)\s+([0-9a-fA-F\-:]{17})\s+(\w+)", re.MULTILINE
    )
    matches = pattern.findall(output)
    
    devices = []
    seen_macs = set()
    
    for ip, mac, entry_type in matches:
        clean_mac = mac.replace(":", "-").upper()
        
        # Skip self, broadcast and multicast entries
        if ip == local_ip:
            continue
        if clean_mac == "FF-FF-FF-FF-FF-FF":
            continue
        if clean_mac.startswith("01-00-5E"):  # IPv4 multicast
            continue
        if ip.startswith("224.") or ip.startswith("239."):
            continue
        if ip.endswith(".255"):
            continue
            
        if clean_mac not in seen_macs:
            seen_macs.add(clean_mac)
            devices.append({
                "ip": ip,
                "mac": clean_mac,
                "type": entry_type,
            })
            
    return devices


def scan_local_network(history_store=None) -> List[Dict[str, str]]:
    """Perform a full LAN scan: sweeps subnet, parses ARP table, resolves hostnames & vendors."""
    net_info = get_local_network_info()
    local_ip = net_info["ip"]
    
    if not local_ip:
        logger.warning("Could not identify local IP for scanning")
        return []
        
    logger.info("Starting LAN scan on interface: %s", local_ip)
    
    # Sweep subnet to refresh ARP cache
    ips = get_subnet_ips(local_ip)
    run_ping_sweep(ips)
    
    # Parse ARP cache
    raw_devices = parse_arp_table(local_ip)
    
    # Resolve details in parallel
    devices = []
    
    def resolve_device_details(dev: Dict[str, str]) -> Dict[str, str]:
        ip = dev["ip"]
        mac = dev["mac"]
        vendor = lookup_vendor(mac)
        hostname = resolve_hostname_safe(ip)
        
        # Fall back to vendor name if no network hostname is registered
        if not hostname:
            if vendor and vendor != "Unknown":
                hostname = f"{vendor} Device"
            else:
                hostname = "Generic Device"
        
        return {
            "mac_address": mac,
            "ip_address": ip,
            "hostname": hostname,
            "vendor": vendor,
        }
        
    with ThreadPoolExecutor(max_workers=16) as executor:
        resolved_devices = list(executor.map(resolve_device_details, raw_devices))
        
    if history_store:
        # Check database for alerts on new devices
        existing_devices = {d["mac_address"]: d for d in history_store.get_devices()}
        history_store.set_all_devices_inactive()
        
        for dev in resolved_devices:
            mac = dev["mac_address"]
            ip = dev["ip_address"]
            hostname = dev["hostname"]
            vendor = dev["vendor"]
            
            # Check if this MAC was never seen before
            if mac not in existing_devices:
                # Log an alert in the database
                title = "New LAN Device Detected"
                msg = f"Device '{hostname or 'Unknown'}' ({ip}) with MAC {mac} ({vendor}) joined the network."
                history_store.save_alert(
                    timestamp=datetime.now(),
                    category="lan_issue",
                    severity="warning",
                    title=title,
                    message=msg
                )
                
            history_store.save_device(
                mac=mac,
                ip=ip,
                hostname=hostname,
                vendor=vendor
            )
            
    return resolved_devices
