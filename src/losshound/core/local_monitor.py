from __future__ import annotations

import csv
import logging
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from typing import List, Dict, Set

from losshound.core.lan_monitor import run_command_resilient, resolve_hostname_safe

logger = logging.getLogger(__name__)

# Enforce 1s default timeout inside local_monitor module initialization
socket.setdefaulttimeout(1.0)

# Local hostname cache to avoid repeated slow lookups
_HOSTNAME_CACHE: Dict[str, str] = {}


def get_pid_to_process_name() -> Dict[int, str]:
    """Get mapping of PID to process name using Windows tasklist."""
    output = run_command_resilient(["tasklist", "/FO", "CSV", "/NH"])
    pid_map = {}
    
    if not output:
        return pid_map
        
    try:
        reader = csv.reader(StringIO(output.strip()))
        for row in reader:
            if len(row) >= 2:
                name = row[0]
                try:
                    pid = int(row[1])
                    pid_map[pid] = name
                except ValueError:
                    continue
    except Exception as exc:
        logger.warning("Error parsing tasklist output: %s", exc)
        
    return pid_map


def get_active_connections() -> List[Dict[str, str]]:
    """Parse netstat -ano to find active external connections."""
    output = run_command_resilient(["netstat", "-ano"])
    
    # Matches TCP/UDP connections
    # Proto  Local Address          Foreign Address        State           PID
    # TCP    192.168.1.5:54321      142.250.74.46:443      ESTABLISHED     4888
    # UDP    0.0.0.0:5353           *:*                                    2140
    pattern = re.compile(
        r"^\s*(TCP|UDP)\s+(\S+)\s+(\S+)(?:\s+([A-Z_]+))?\s+(\d+)\s*$", re.IGNORECASE
    )
    
    pid_map = get_pid_to_process_name()
    connections = []
    
    # We resolve hostnames of unique remote IPs in a thread pool to avoid GUI freeze
    unique_ips: Set[str] = set()
    
    lines = output.splitlines()
    for line in lines:
        match = pattern.match(line)
        if not match:
            continue
            
        proto = match.group(1).upper()
        local_addr = match.group(2)
        remote_addr = match.group(3)
        state = match.group(4) or ""
        pid_str = match.group(5)
        
        try:
            pid = int(pid_str)
        except ValueError:
            continue
            
        # Parse remote IP and port
        if ":" in remote_addr:
            remote_ip, _, remote_port = remote_addr.rpartition(":")
            remote_ip = remote_ip.strip("[]")
        else:
            remote_ip = remote_addr
            remote_port = ""
            
        # Filter out listening, loopback, and broadcast addresses
        if remote_ip in ("0.0.0.0", "[::]", "::", "*", "127.0.0.1", "::1", "[::1]", ""):
            continue
        if remote_port in ("*", "0") or not remote_port or state == "LISTENING":
            continue
            
        proc_name = pid_map.get(pid, "Unknown")
        
        # Track unique remote IPs for hostname lookup
        if remote_ip not in _HOSTNAME_CACHE:
            unique_ips.add(remote_ip)
            
        connections.append({
            "process": proc_name,
            "pid": str(pid),
            "protocol": proto,
            "local_address": local_addr,
            "remote_ip": remote_ip,
            "remote_port": remote_port,
            "state": state,
        })
        
    # Resolve hostnames for newly seen remote IPs in parallel (1s timeout)
    if unique_ips:
        with ThreadPoolExecutor(max_workers=10) as executor:
            # map remote IPs to lookup function
            results = list(executor.map(resolve_hostname_safe, unique_ips))
            for ip, name in zip(unique_ips, results):
                _HOSTNAME_CACHE[ip] = name if name else ip
                
    # Attach resolved domain names to connections list
    for conn in connections:
        ip = conn["remote_ip"]
        conn["resolved_name"] = _HOSTNAME_CACHE.get(ip, ip)
        
    return connections
