"""
Detection history: periodically persist Ruckus One detection accuracy snapshots.

A background sampler runs the R1 correlation on a fixed interval (regardless of
whether the UI is open) and writes per-personality + overall rows to the
detection_snapshots table, turning instantaneous "hit or miss" into a trend.
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from ..db import SessionLocal
from ..models.db_models import DetectionSnapshotModel

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL = int(os.environ.get("DETECTION_SNAPSHOT_INTERVAL", "60"))  # seconds
RETENTION_DAYS = int(os.environ.get("DETECTION_RETENTION_DAYS", "30"))


def _extract_interfaces(pi_statuses: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten Pi statuses into a list of interface dicts tagged with pi_id."""
    interfaces: List[Dict[str, Any]] = []
    for pi_id, pi_status in pi_statuses.items():
        pi_dict = pi_status.dict() if hasattr(pi_status, "dict") else pi_status
        for iface in pi_dict.get("interfaces", []):
            iface = iface.copy()
            iface["pi_id"] = pi_id
            interfaces.append(iface)
    return interfaces


def persist_snapshot(db, result: Dict[str, Any], when: datetime) -> int:
    """Write one snapshot (overall + per-personality rows) from a correlation result."""
    stats = result.get("detection_stats", {})
    rows = [
        DetectionSnapshotModel(
            timestamp=when,
            personality="__overall__",
            total=stats.get("total", 0),
            detected_correctly=stats.get("detected_correctly", 0),
            detected_incorrectly=stats.get("detected_incorrectly", 0),
            not_detected=stats.get("not_detected", 0),
            detected_as="{}",
        )
    ]
    for personality, ps in stats.get("by_personality", {}).items():
        rows.append(
            DetectionSnapshotModel(
                timestamp=when,
                personality=personality,
                total=ps.get("total", 0),
                detected_correctly=ps.get("detected_correctly", 0),
                detected_incorrectly=ps.get("detected_incorrectly", 0),
                not_detected=ps.get("not_detected", 0),
                detected_as=json.dumps(ps.get("detected_as", {})),
            )
        )
    db.add_all(rows)
    db.commit()
    return len(rows)


def _prune(db, when: datetime) -> None:
    cutoff = when - timedelta(days=RETENTION_DAYS)
    db.query(DetectionSnapshotModel).filter(
        DetectionSnapshotModel.timestamp < cutoff
    ).delete(synchronize_session=False)
    db.commit()


async def detection_sampler_loop(app, get_monitor) -> None:
    """Background task: sample R1 detection accuracy every SNAPSHOT_INTERVAL seconds.

    get_monitor: zero-arg callable returning a RuckusOneMonitor or None when R1
    is not configured. Sampling is skipped (cheaply) while unconfigured.
    """
    logger.info(f"Detection sampler started (interval={SNAPSHOT_INTERVAL}s, retention={RETENTION_DAYS}d)")
    while True:
        try:
            await asyncio.sleep(SNAPSHOT_INTERVAL)

            monitor = get_monitor()
            monitoring = getattr(app.state, "monitoring", None)
            if not monitor or not monitoring:
                continue

            interfaces = _extract_interfaces(monitoring.get_all_statuses())
            if not interfaces:
                continue

            # R1 client fetch is blocking (requests) — keep the event loop free.
            result = await asyncio.to_thread(monitor.get_correlated_status, interfaces)

            when = datetime.utcnow()
            db = SessionLocal()
            try:
                n = persist_snapshot(db, result, when)
                _prune(db, when)
            finally:
                db.close()

            stats = result.get("detection_stats", {})
            logger.debug(
                f"Detection snapshot saved ({n} rows): "
                f"{stats.get('detected_correctly', 0)}/{stats.get('total', 0)} correct, "
                f"{stats.get('not_detected', 0)} not_detected"
            )
        except asyncio.CancelledError:
            logger.info("Detection sampler stopped")
            raise
        except Exception as e:
            logger.error(f"Detection sampler error: {e}")
