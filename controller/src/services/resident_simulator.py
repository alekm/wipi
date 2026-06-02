"""
Resident Simulator Service - Drives long-running resident-style traffic.
"""
import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Callable

from sqlalchemy.orm import Session

from shared.models import Scenario, PiAssignment, PiInterfaceAssignment, TrafficConfig
from .pi_manager import PiManager
from .scenario_manager import ScenarioManager
from .psk_manager import PskManager
from ..models import ResidentSimulationConfigModel

logger = logging.getLogger(__name__)


@dataclass
class ResidentSimulationConfig:
  """In-memory configuration for resident simulation."""
  enabled: bool = False
  psk_set_id: Optional[str] = None
  target_active_apartments: int = 64  # Default target for standard deployment
  rotation_hours: float = 6.0
  max_interfaces_per_pi: int = 8  # Pi 5 supports up to 8 interfaces (base + VIFs)


@dataclass
class ResidentSimulationStatus:
  enabled: bool
  psk_set_id: Optional[str]
  target_active_apartments: int
  rotation_hours: float
  max_interfaces_per_pi: int
  active_apartments: int
  total_apartments: int
  last_rotation_at: Optional[datetime]
  next_rotation_at: Optional[datetime]


class ResidentSimulator:
  """
  Background service that periodically (re)builds a scenario assigning
  apartments (PSK entries) to Pis/interfaces and applies it, using a
  simple diurnal traffic profile.
  """

  def __init__(
      self,
      pi_manager: PiManager,
      scenario_manager: ScenarioManager,
      psk_manager: PskManager,
      orchestrator,
      db_session_maker: Callable[[], Session],
      scenario_id: str = "resident-sim",
  ):
    self.pi_manager = pi_manager
    self.scenario_manager = scenario_manager
    self.psk_manager = psk_manager
    self.orchestrator = orchestrator
    self.db_session_maker = db_session_maker
    self.scenario_id = scenario_id

    self.config = ResidentSimulationConfig()
    self.running = False
    self._task: Optional[asyncio.Task] = None
    self._current_indices: List[int] = []
    self._last_rotation_at: Optional[datetime] = None

    # Load persisted config from database
    self._load_config()

    logger.info("ResidentSimulator initialized")

  async def start(self) -> None:
    """Start the resident simulation loop if enabled."""
    if self.running:
      logger.warning("Resident simulator already running")
      return
    if not self.config.enabled:
      logger.info("Resident simulator config disabled; not starting loop")
      return
    self.running = True
    self._task = asyncio.create_task(self._loop())
    logger.info("Resident simulator loop started")

  async def rotate_now(self) -> None:
    """Manually trigger an immediate rotation (generate and apply new scenario)."""
    logger.info("Manual rotation triggered")
    await self._apply_once()

  async def stop(self) -> None:
    """Stop the resident simulation loop."""
    if not self.running:
      return
    self.running = False
    if self._task:
      self._task.cancel()
      try:
        await self._task
      except asyncio.CancelledError:
        pass
      self._task = None
    logger.info("Resident simulator loop stopped")

  def update_config(self, new_config: ResidentSimulationConfig) -> None:
    """Update simulation configuration and persist to database."""
    self.config = new_config
    self._persist_config()
    logger.info(
      "Resident simulator config updated: enabled=%s, psk_set_id=%s, target=%s, rotation_hours=%s",
      new_config.enabled,
      new_config.psk_set_id,
      new_config.target_active_apartments,
      new_config.rotation_hours,
    )

  def get_status(self) -> ResidentSimulationStatus:
    """Return current status snapshot."""
    total_apartments = 0
    try:
      # Light-weight read without holding open a session long-term.
      db = self.db_session_maker()
      try:
        if self.config.psk_set_id:
          psk_set = self.psk_manager.get_psk_set(db, self.config.psk_set_id)
          if psk_set:
            total_apartments = len(psk_set.psks)
      finally:
        db.close()
    except Exception as e:
      logger.warning(f"Error computing resident simulator status: {e}")

    next_rotation_at = None
    if self._last_rotation_at and self.config.rotation_hours > 0:
      next_rotation_at = self._last_rotation_at + timedelta(hours=self.config.rotation_hours)

    return ResidentSimulationStatus(
      enabled=self.config.enabled and self.running,
      psk_set_id=self.config.psk_set_id,
      target_active_apartments=self.config.target_active_apartments,
      rotation_hours=self.config.rotation_hours,
      max_interfaces_per_pi=self.config.max_interfaces_per_pi,
      active_apartments=len(self._current_indices),
      total_apartments=total_apartments,
      last_rotation_at=self._last_rotation_at,
      next_rotation_at=next_rotation_at,
    )

  async def _loop(self) -> None:
    """Main loop: periodically rebuild and apply scenario."""
    logger.info("Resident simulator main loop running")
    while self.running and self.config.enabled:
      try:
        await self._apply_once()
      except asyncio.CancelledError:
        logger.info("Resident simulator loop cancelled")
        break
      except Exception as e:
        logger.error(f"Error in resident simulator loop: {e}")

      # Sleep until next rotation. If no apartments are currently active (e.g.
      # no Pis were online), retry more frequently so that newly-online Pis
      # start getting traffic quickly.
      if not self._current_indices:
        sleep_seconds = 60  # retry every minute when nothing is active
      else:
        sleep_seconds = max(60, int(self.config.rotation_hours * 3600))

      await asyncio.sleep(sleep_seconds)

    logger.info("Resident simulator main loop exiting")

  async def _apply_once(self) -> None:
    """Compute a fresh scenario and apply it via orchestrator."""
    db = self.db_session_maker()
    try:
      if not self.config.psk_set_id:
        logger.warning("Resident simulator has no psk_set_id; skipping apply")
        return

      psk_set = self.psk_manager.get_psk_set(db, self.config.psk_set_id)
      if not psk_set or not psk_set.psks:
        logger.warning("Resident simulator PSK set %s missing or empty", self.config.psk_set_id)
        return

      # Determine online Pis and capacity
      online_pis = self.pi_manager.get_online_pis(db)
      if not online_pis:
        logger.warning("Resident simulator: no online Pis available")
        return

      # Calculate total capacity based on actual Pi capabilities
      max_slots = 0
      for pi in online_pis:
        # Try new format first (total_capacity from all interfaces)
        pi_capacity = pi.capabilities.get("total_capacity")

        if pi_capacity is None:
          # Fall back to legacy format (single max_interfaces)
          pi_capacity = pi.capabilities.get("max_interfaces", self.config.max_interfaces_per_pi)

        # Don't exceed the configured maximum per Pi
        pi_capacity = min(pi_capacity, self.config.max_interfaces_per_pi)
        max_slots += pi_capacity

        logger.debug(f"Pi {pi.pi_id}: capacity={pi_capacity}")

      logger.info(f"Total capacity across {len(online_pis)} Pis: {max_slots} interfaces")

      if max_slots == 0:
        logger.warning("Resident simulator: max_slots is 0")
        return

      target = min(self.config.target_active_apartments, max_slots, len(psk_set.psks))
      if target <= 0:
        logger.info("Resident simulator: target_active_apartments <= 0; skipping")
        return

      # Pick apartment indices (PSK indices)
      available_indices = list(range(len(psk_set.psks)))
      if target >= len(available_indices):
        indices = available_indices
      else:
        indices = random.sample(available_indices, target)

      self._current_indices = indices
      self._last_rotation_at = datetime.utcnow()

      # Persist rotation timestamp to database
      self._persist_config()

      # Build Scenario
      scenario = self._build_scenario(psk_set, online_pis, indices)

      # Persist scenario (create or update)
      existing = self.scenario_manager.get_scenario(db, self.scenario_id)
      if existing:
        scenario.id = self.scenario_id
        self.scenario_manager.update_scenario(db, self.scenario_id, scenario)
      else:
        scenario.id = self.scenario_id
        self.scenario_manager.create_scenario(db, scenario)

      # Store desired config (non-blocking, pure pull-based architecture)
      # Agents will poll /api/pis/{pi_id}/configuration and apply autonomously
      success = self.orchestrator.set_desired_scenario(db, self.scenario_id)

      if success:
        logger.info(
          "Resident simulator set desired config for scenario %s with %d active apartments on %d Pis",
          self.scenario_id,
          len(indices),
          len(online_pis),
        )
      else:
        logger.error(
          "Resident simulator failed to set desired config for scenario %s",
          self.scenario_id,
        )
    finally:
      db.close()

  # Common device personalities for realistic fingerprinting
  # Samsung replaced with Android (per user request)
  # Removed Windows10 (detection issues)
  DEVICE_PERSONALITIES = [
    "iphone",      # 25% - iOS devices (working)
    "iphone",
    "iphone",
    # Android family split 3 ways (A/B/C experiment): each has a distinct DHCP
    # fingerprint, all score as "Android". /history reveals which Ruckus detects best.
    "android",     # generic Android, option-55 1,121,33,3,6,28,51,58,59
    "android",
    "samsung",     # Samsung variant, option-55 1,3,6,15,28,33,51,58,59,121 (docs: most validated)
    "samsung",
    "pixel",       # Pixel variant, option-55 1,3,6,15,26,28,51,58,59
    "pixel",
    "ipad",        # 15% - iPads (working)
    "ipad",
    "macos",       # 10% - macOS laptops
  ]

  # User-Agent strings matching DHCP personalities for HTTP traffic fingerprinting
  USER_AGENT_MAP = {
    "iphone": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "ipad": "Mozilla/5.0 (iPad; CPU OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "android": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "samsung": "Mozilla/5.0 (Linux; Android 14; SM-S911U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "pixel": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "macos": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "macbook": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "windows10": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "windows11": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  }

  def _build_scenario(self, psk_set, pis: List, indices: List[int]) -> Scenario:
    """
    Build a Scenario assigning each selected PSK index to a Pi/interface,
    with a simple diurnal traffic profile.

    Distributes interfaces across all available wireless adapters on each Pi,
    using both base interfaces and VIFs up to hardware limits.
    """
    pi_assignments: List[PiAssignment] = []
    # Clone indices we can pop from
    remaining = list(indices)

    now = datetime.utcnow()
    for pi in pis:
      if not remaining:
        break

      interfaces: List[PiInterfaceAssignment] = []

      # Get Pi's interface capabilities
      # New format: {"interfaces": [{"name": "wlan0", "max_interfaces": 2}, ...], "total_capacity": 4}
      # Legacy format: {"base_interface": "wlan0", "max_interfaces": 2}
      pi_iface_caps = pi.capabilities.get("interfaces", [])

      if not pi_iface_caps:
        # Legacy format - single base interface
        base_iface = pi.capabilities.get("base_interface", "wlan0")
        max_count = pi.capabilities.get("max_interfaces", self.config.max_interfaces_per_pi)
        max_count = min(max_count, self.config.max_interfaces_per_pi)
        pi_iface_caps = [{"name": base_iface, "max_interfaces": max_count}]

      # Distribute PSKs across all available interfaces on this Pi
      for iface_cap in pi_iface_caps:
        if not remaining:
          break

        iface_name = iface_cap["name"]
        max_count = iface_cap["max_interfaces"]
        # Respect configured maximum
        max_count = min(max_count, self.config.max_interfaces_per_pi)

        # Assign interfaces for this physical adapter
        # First: base interface (wlan0, wlan1, etc.)
        # Then: VIFs (wlan0_1, wlan1_1, etc.) up to max_count
        for idx in range(max_count):
          if not remaining:
            break

          psk_index = remaining.pop()

          # Generate interface name
          if idx == 0:
            # Use base interface directly
            assigned_name = iface_name
          else:
            # Create VIF name: wlan0_1, wlan0_2, etc.
            assigned_name = f"{iface_name}_{idx}"

          # Assign random device personality for DHCP fingerprinting
          personality = random.choice(self.DEVICE_PERSONALITIES)

          # Generate traffic config with matching user agent
          traffic_cfg = self._make_traffic_config(now, personality)

          # Use psk_set_id + psk_index (no plaintext password); orchestrator resolves at apply time
          interfaces.append(
            PiInterfaceAssignment(
              name=assigned_name,
              ssid=psk_set.ssid or "",
              psk_set_id=psk_set.id,
              psk_index=psk_index,
              mac_address=None,
              dhcp_personality=personality,
              traffic=traffic_cfg,
            )
          )

      if interfaces:
        pi_assignments.append(
          PiAssignment(
            pi_id=pi.pi_id,
            interfaces=interfaces,
          )
        )

    return Scenario(
      id=self.scenario_id,
      name="Resident Traffic Simulation",
      description="Auto-generated scenario simulating resident traffic from apartment PSKs",
      pis=pi_assignments,
    )

  def _make_traffic_config(self, now: datetime, personality: str) -> Optional[TrafficConfig]:
    """
    Create aggressive, diverse time-of-day based traffic configuration.

    - Night (0–5): light activity, some streamers
    - Day (6–17): moderate browsing and streaming
    - Evening (18–23): HEAVY streaming and downloads (peak usage)

    Args:
        now: Current datetime for time-of-day calculation
        personality: DHCP personality (e.g., "iphone", "android") for User-Agent matching
    """
    hour = now.hour

    # Get matching User-Agent for this personality
    user_agent = self.USER_AGENT_MAP.get(personality, self.USER_AGENT_MAP.get("android"))

    # Choose time-of-day band
    if 0 <= hour < 6:
      band = "night"
    elif 6 <= hour < 18:
      band = "day"
    else:
      band = "evening"

    # Decide traffic role with DIVERSE application mix:
    # browser / video_stream / audio_stream / api_polling / bulk
    r = random.random()
    if band == "night":
      # Night: 30% browser, 25% video, 25% audio, 10% api, 10% bulk
      if r < 0.30:
        role = "browser"
      elif r < 0.55:
        role = "stream"
      elif r < 0.80:
        role = "audio"
      elif r < 0.90:
        role = "api"
      else:
        role = "bulk"
    elif band == "day":
      # Day: 25% browser, 30% video, 20% audio, 15% api, 10% bulk
      if r < 0.25:
        role = "browser"
      elif r < 0.55:
        role = "stream"
      elif r < 0.75:
        role = "audio"
      elif r < 0.90:
        role = "api"
      else:
        role = "bulk"
    else:
      # Evening PEAK: 20% browser, 40% video, 15% audio, 15% api, 10% bulk
      if r < 0.20:
        role = "browser"
      elif r < 0.60:
        role = "stream"
      elif r < 0.75:
        role = "audio"
      elif r < 0.90:
        role = "api"
      else:
        role = "bulk"

    if role == "browser":
      # AGGRESSIVE HTTP browsing - much shorter intervals
      if band == "night":
        interval = random.randint(30, 90)   # Was 180-300
      elif band == "day":
        interval = random.randint(15, 60)   # Was 60-180
      else:  # evening
        interval = random.randint(10, 30)   # Was 30-120

      # More diverse URLs for better app detection
      urls = [
        "https://www.youtube.com",
        "https://www.reddit.com",
        "https://news.ycombinator.com",
        "https://www.wikipedia.org",
        "https://www.amazon.com",
        "https://www.netflix.com",
        "https://www.spotify.com",
        "https://www.facebook.com",
        "https://www.instagram.com",
        "https://www.twitter.com",
        "https://www.github.com",
        "https://www.stackoverflow.com",
      ]

      return TrafficConfig(
        type="http_browser",
        config={
          "urls": urls,
          "interval": interval,
          "timeout": 10,
          "user_agent": user_agent,
        },
      )

    if role == "stream":
      # AGGRESSIVE YouTube streaming - higher quality, longer sessions
      if band == "night":
        quality = "480p"  # Was 360p
        watch_min = 600   # 10 min (was 5)
        watch_max = 1800  # 30 min (was 15)
      elif band == "day":
        quality = "720p"  # Was 480p
        watch_min = 900   # 15 min (was 10)
        watch_max = 2700  # 45 min (was 30)
      else:
        quality = "1080p"  # Was 720p - FULL HD streaming
        watch_min = 1800   # 30 min (was 15)
        watch_max = 5400   # 90 min (was 45) - binge watching!

      return TrafficConfig(
        type="youtube",
        config={
          "quality": quality,
          "watch_duration_min": watch_min,
          "watch_duration_max": watch_max,
          "pause_between_min": 5,    # Reduced from 10
          "pause_between_max": 30,   # Reduced from 60
          "user_agent": user_agent,
        },
      )

    if role == "audio":
      # STREAMING AUDIO - continuous music streaming (Spotify/Apple Music style)
      if band == "night":
        quality = "normal"      # 160 kbps
        session_min = 1800      # 30 min
        session_max = 3600      # 1 hour
      elif band == "day":
        quality = "high"        # 320 kbps
        session_min = 3600      # 1 hour
        session_max = 7200      # 2 hours
      else:
        quality = "high"        # 320 kbps - premium quality
        session_min = 5400      # 1.5 hours
        session_max = 10800     # 3 hours - long listening sessions

      return TrafficConfig(
        type="streaming_audio",
        config={
          "quality": quality,
          "session_duration_min": session_min,
          "session_duration_max": session_max,
          "pause_between_min": 10,
          "pause_between_max": 120,
          "user_agent": user_agent,
        },
      )

    if role == "api":
      # API POLLING - frequent background activity (social media, messaging apps)
      if band == "night":
        poll_min = 15           # Slower polling at night
        poll_max = 60
      elif band == "day":
        poll_min = 10           # Moderate polling during day
        poll_max = 45
      else:
        poll_min = 5            # AGGRESSIVE polling during peak - very active
        poll_max = 20

      return TrafficConfig(
        type="api_polling",
        config={
          "poll_interval_min": poll_min,
          "poll_interval_max": poll_max,
          "burst_mode": True,   # Enable burst polling
          "timeout": 10,
          "user_agent": user_agent,
        },
      )

    # AGGRESSIVE bulk transfers - higher bandwidth
    # Using Hetzner's US speed test server with valid SSL certificate
    # Alternative: https://fsn-speed.hetzner.com/100MB.bin (Germany)
    url = "https://ash-speed.hetzner.com/100MB.bin"

    # Much higher bandwidth limits
    if band == "night":
      max_bw = "5mbps"   # Was 3mbps
    elif band == "day":
      max_bw = "8mbps"   # Was 3mbps
    else:
      max_bw = "15mbps"  # Was 5mbps - HEAVY downloads during peak

    return TrafficConfig(
      type="bulk_transfer",
      config={
        "url": url,
        "direction": "download",
        "repeat": True,
        "max_bandwidth": max_bw,
        "user_agent": user_agent,
      },
    )

  def _load_config(self) -> None:
    """Load persisted configuration from database on startup."""
    try:
      db = self.db_session_maker()
      try:
        config_model = db.query(ResidentSimulationConfigModel).first()
        if config_model:
          self.config = ResidentSimulationConfig(
            enabled=config_model.enabled,
            psk_set_id=config_model.psk_set_id,
            target_active_apartments=config_model.target_active_apartments,
            rotation_hours=config_model.rotation_hours,
            max_interfaces_per_pi=config_model.max_interfaces_per_pi,
          )
          self._last_rotation_at = config_model.last_rotation_at
          logger.info(
            f"Loaded persisted config: enabled={self.config.enabled}, "
            f"psk_set_id={self.config.psk_set_id}, "
            f"target={self.config.target_active_apartments}"
          )
        else:
          logger.info("No persisted config found, using defaults")
      finally:
        db.close()
    except Exception as e:
      logger.error(f"Error loading persisted config: {e}")

  def _persist_config(self) -> None:
    """Persist current configuration to database."""
    try:
      db = self.db_session_maker()
      try:
        config_model = db.query(ResidentSimulationConfigModel).first()

        # Calculate next rotation time
        next_rotation_at = None
        if self._last_rotation_at and self.config.rotation_hours > 0:
          next_rotation_at = self._last_rotation_at + timedelta(hours=self.config.rotation_hours)

        if config_model:
          # Update existing
          config_model.enabled = self.config.enabled
          config_model.psk_set_id = self.config.psk_set_id
          config_model.target_active_apartments = self.config.target_active_apartments
          config_model.rotation_hours = self.config.rotation_hours
          config_model.max_interfaces_per_pi = self.config.max_interfaces_per_pi
          config_model.last_rotation_at = self._last_rotation_at
          config_model.next_rotation_at = next_rotation_at
        else:
          # Create new
          config_model = ResidentSimulationConfigModel(
            enabled=self.config.enabled,
            psk_set_id=self.config.psk_set_id,
            target_active_apartments=self.config.target_active_apartments,
            rotation_hours=self.config.rotation_hours,
            max_interfaces_per_pi=self.config.max_interfaces_per_pi,
            last_rotation_at=self._last_rotation_at,
            next_rotation_at=next_rotation_at,
          )
          db.add(config_model)

        db.commit()
        logger.debug("Persisted config to database")
      finally:
        db.close()
    except Exception as e:
      logger.error(f"Error persisting config: {e}")

