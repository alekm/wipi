# Orb Network Quality Monitoring

WiPi agents report real-time internet-quality metrics measured by [Orb](https://orb.net),
a network observability sensor by the founder of Ookla/Speedtest. This gives a
per-Pi view of the connection each Pi actually rides on — for WiPi Pis that is
the DPSK Wi-Fi client interface, so Orb measures the *simulated client's*
experience, not just the wired management uplink.

## How it works

```
orb sensor (per Pi) ──`orb summary`──> agent ──AgentStatus.orb──> controller ──/pis/{id}/status──> UI
```

1. **Orb sensor** runs on each Pi as a systemd service (`orb.service`), continuously
   measuring over the Pi's default route.
2. **Agent** (`agent/src/core/orb_collector.py`) shells out to `orb summary`, parses
   the JSON, and folds a compact metrics dict into `AgentStatus.orb`.
3. **Controller** caches agent status via the monitoring service and exposes it at
   `GET /api/pis/{pi_id}/status`.
4. **UI** renders a "Network Quality (Orb)" section in the Pi Fleet details panel.

### No Orb Cloud account required

`orb summary` reads the **local** sensor directly over its on-device API, so:

- **No cloud account or sensor linking is needed.** This sidesteps the Orb free-plan
  5-sensor *cloud* cap entirely — WiPi runs Orb on every Pi regardless of fleet size.
- No data is required to leave the device.

> Orb measures whatever interface holds the Pi's **default route**. On WiPi Pis this is
> normally the DPSK Wi-Fi client (`wlan0`/`wlan1`); on a Pi whose default route is the
> wired uplink it will measure `eth0` instead. The `measured_interface`/`measured_ssid`
> fields report which.

## Installing the Orb sensor on a Pi

```bash
# On the Pi (Raspberry Pi OS / Debian / Ubuntu, etc.)
curl -fsSL https://pkgs.orb.net/install.sh | sh
```

This installs the `orb` package (binary at `/usr/bin/orb`), runs the sensor as the
`orb` system user, and starts measuring immediately. Verify:

```bash
sudo -u orb orb summary | jq .orb_score.display   # 0-100 score once a window completes
```

No further configuration is needed. The agent (running as root) reads the sensor via
`orb summary` with `HOME=/home/orb` so it can use the sensor's local credentials.

## Metrics reported

`AgentStatus.orb` is a compact dict (null when Orb is not installed):

| Field | Meaning |
|-------|---------|
| `orb_score` | Overall Orb Score, 0–100 |
| `responsiveness_score` | Responsiveness sub-score, 0–100 |
| `reliability_score` | Reliability sub-score, 0–100 |
| `bandwidth_score` | Bandwidth sub-score, 0–100 |
| `download_mbps` / `upload_mbps` | Measured throughput |
| `lag_ms` | Internet lag (latency under load) |
| `measured_interface` | Interface Orb measured over (e.g. `wlan0`, `eth0`) |
| `measured_ssid` | SSID if measured over Wi-Fi |
| `measured_link_type` | `WiFi` / `Ethernet` |
| `public_ip` | Public IP seen by the sensor |
| `isp` | ISP name (GeoIP) |
| `collected_ts` | Sensor timestamp (epoch ms) |

## Implementation notes

- **Collection runs in a worker thread.** `orb summary` is invoked via `subprocess.run`
  inside `asyncio.to_thread`; `asyncio.create_subprocess_exec` raises
  `NotImplementedError` under the agent's uvicorn event loop (no child watcher).
- **Cached for 30s** (`ORB_CACHE_TTL`) so frequent status polls don't spawn a process
  each time. Collection **fails safe to `None`** — a missing binary, timeout, or parse
  error never breaks the status endpoint, and a missing binary disables further attempts.
- **Configurable via env:** `ORB_BIN` (`/usr/bin/orb`), `ORB_HOME` (`/home/orb`),
  `ORB_SUMMARY_TIMEOUT` (10s), `ORB_CACHE_TTL` (30s).

## Viewing in the UI

Pi Fleet → select a Pi → **Network Quality (Orb)** section: color-coded Orb Score,
download/upload, latency, reliability/responsiveness, and the measured interface/SSID/ISP.
The "(Orb)" label links to [orb.net](https://orb.net).
