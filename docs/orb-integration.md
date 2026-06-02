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

### Licensing & consent gate

`orb summary` reads the **local** sensor and would technically work on an *unlinked*
sensor — which means it could be used to run sensors at scale and bypass Orb's
per-device plan cap. **WiPi deliberately does not do that.** Out of respect for Orb's
plan-based licensing, the agent collects and reports Orb metrics **only when a
deployment token is configured** (i.e. the sensor has been linked to your own Orb
account). With no token, the integration stays dormant and `AgentStatus.orb` is `null`.

The agent looks for `ORB_DEPLOYMENT_TOKEN` in its environment or in `ORB_ENV_FILE`
(default `/etc/default/orb`). The check runs every cycle, so adding a token enables
collection without restarting the agent.

> This gate is trivially bypassable — it's a good-faith default, not DRM. Please
> license your sensors: the [Orb free plan](https://orb.net/plans) covers 5 devices,
> paid plans cover more.

> Orb measures whatever interface holds the Pi's **default route**. On WiPi Pis this is
> normally the DPSK Wi-Fi client (`wlan0`/`wlan1`); on a Pi whose default route is the
> wired uplink it will measure `eth0` instead. The `measured_interface`/`measured_ssid`
> fields report which.

## Installing & linking the Orb sensor on a Pi

```bash
# On the Pi (Raspberry Pi OS / Debian / Ubuntu, etc.)
curl -fsSL https://pkgs.orb.net/install.sh | sh
```

This installs the `orb` package (binary at `/usr/bin/orb`) and runs the sensor as the
`orb` system user. Then **link the sensor to your Orb account** — this both keeps you
compliant with Orb's licensing and activates the WiPi integration (see the licensing
gate above). Create a deployment token in Orb Cloud (Orchestration → API Keys) and add
it to the sensor's environment file:

```bash
# /etc/default/orb  (root-owned, chmod 600 — this is a secret, never commit it)
ORB_DEPLOYMENT_TOKEN=orb-dt1-xxxxxxxxxxxxxxxx
ORB_EPHEMERAL_MODE=1            # recommended on SD-card Pis to reduce flash wear
```

```bash
sudo systemctl restart orb
sudo journalctl -u orb | grep "deployment token applied successfully"   # confirm link
sudo -u orb orb summary | jq .orb_score.display                          # 0-100 once warmed up
```

The agent (running as root) reads the sensor via `orb summary` with `HOME=/home/orb`,
and reports metrics only once the deployment token is present.

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
- **Licensing gate** (see above): collection is skipped entirely unless an
  `ORB_DEPLOYMENT_TOKEN` is found in the agent env or `ORB_ENV_FILE`.
- **Configurable via env:** `ORB_BIN` (`/usr/bin/orb`), `ORB_HOME` (`/home/orb`),
  `ORB_SUMMARY_TIMEOUT` (10s), `ORB_CACHE_TTL` (30s), `ORB_ENV_FILE` (`/etc/default/orb`).

## Viewing in the UI

Pi Fleet → select a Pi → **Network Quality (Orb)** section: color-coded Orb Score,
download/upload, latency, reliability/responsiveness, and the measured interface/SSID/ISP.
The "(Orb)" label links to [orb.net](https://orb.net).
