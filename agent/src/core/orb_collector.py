"""
Orb (orb.net) network-quality collector.

Runs the locally-installed Orb sensor's `orb summary` command and extracts a
compact set of metrics for inclusion in the agent status payload.

No Orb Cloud account is required: `orb summary` connects to the local sensor
service and returns JSON directly, so this works on any number of Pis without
the free-plan 5-sensor cloud cap. Orb measures over the Pi's default route,
which on WiPi Pis is the DPSK WiFi client interface (wlan0).
"""
import os
import json
import time
import asyncio
import logging
import subprocess
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ORB_BIN = os.environ.get("ORB_BIN", "/usr/bin/orb")
ORB_HOME = os.environ.get("ORB_HOME", "/home/orb")  # where the sensor's config/cert live
ORB_TIMEOUT = float(os.environ.get("ORB_SUMMARY_TIMEOUT", "10"))
ORB_CACHE_TTL = float(os.environ.get("ORB_CACHE_TTL", "30"))  # avoid spawning on every poll

# Module-level cache: (timestamp, value). value None means "collected, no data".
_cache: tuple[float, Optional[Dict[str, Any]]] = (0.0, None)
_unavailable: bool = False  # set once if the orb binary is missing


def _extract(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten the verbose `orb summary` JSON into a compact metrics dict."""
    score = summary.get("orb_score", {}) or {}
    comps = score.get("components", {}) or {}
    bw = (comps.get("bandwidth_score", {}) or {}).get("components", {}) or {}
    resp = (comps.get("responsiveness_score", {}) or {}).get("components", {}) or {}
    rel = comps.get("reliability_score", {}) or {}

    tags = summary.get("tags", {}) or {}
    ni = tags.get("network_interface", {}) or {}
    geo = tags.get("geoip", {}) or {}

    def _val(d: Dict[str, Any], key: str) -> Optional[float]:
        node = d.get(key)
        return node.get("value") if isinstance(node, dict) else None

    dl_kbps = _val(bw, "download_bandwidth_kbps")
    ul_kbps = _val(bw, "upload_bandwidth_kbps")
    lag_us = _val(resp, "internet_lag_us")

    return {
        "orb_score": score.get("display"),
        "responsiveness_score": (comps.get("responsiveness_score", {}) or {}).get("display"),
        "reliability_score": rel.get("display"),
        "bandwidth_score": (comps.get("bandwidth_score", {}) or {}).get("display"),
        "download_mbps": round(dl_kbps / 1000, 1) if dl_kbps is not None else None,
        "upload_mbps": round(ul_kbps / 1000, 1) if ul_kbps is not None else None,
        "lag_ms": round(lag_us / 1000, 1) if lag_us is not None else None,
        "measured_interface": ni.get("iface_name"),
        "measured_ssid": ni.get("name"),
        "measured_link_type": ni.get("type"),
        "public_ip": tags.get("public_ip"),
        "isp": geo.get("isp_name"),
        "collected_ts": summary.get("created_ts"),
    }


async def get_orb_summary() -> Optional[Dict[str, Any]]:
    """Return compact Orb metrics, or None if Orb is unavailable.

    Cached for ORB_CACHE_TTL seconds so frequent status polls don't spawn a
    process each time. Never raises — failures degrade to None.
    """
    global _cache, _unavailable

    if _unavailable:
        return None

    now = time.monotonic()
    cached_at, cached_val = _cache
    if now - cached_at < ORB_CACHE_TTL:
        return cached_val

    try:
        # Run the blocking command in a thread. asyncio.create_subprocess_exec
        # can raise NotImplementedError under some uvicorn event loops (no child
        # watcher), so subprocess.run in a worker thread is more portable.
        stdout = await asyncio.to_thread(_run_summary)
        if not stdout:
            _cache = (now, None)
            return None

        summary = json.loads(stdout)
        value = _extract(summary)
        _cache = (now, value)
        return value

    except FileNotFoundError:
        # orb not installed on this Pi — stop trying.
        logger.info("Orb binary not found at %s; Orb metrics disabled", ORB_BIN)
        _unavailable = True
        return None
    except Exception as e:
        logger.warning("Failed to collect orb summary: %r", e)
        _cache = (now, None)
        return None


def _run_summary() -> Optional[str]:
    """Run `orb summary` synchronously and return stdout (JSON), or None.

    Raises FileNotFoundError if the orb binary is missing (handled by caller).
    """
    env = {**os.environ, "HOME": ORB_HOME}  # orb finds its cert/config via HOME
    result = subprocess.run(
        [ORB_BIN, "summary"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,  # orb logs to stderr; JSON is on stdout
        env=env,
        timeout=ORB_TIMEOUT,
    )
    if result.returncode != 0 or not result.stdout:
        logger.debug("orb summary returned %s with no data", result.returncode)
        return None
    return result.stdout.decode()
