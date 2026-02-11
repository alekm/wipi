"""
Shared API contract models for WiPi system.
Used by both controller and agent to ensure consistency.
"""
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# Traffic Configuration Models
class TrafficConfig(BaseModel):
    """Base traffic configuration"""
    type: Literal["http_browser", "video_stream", "bulk_transfer", "idle", "speedtest", "youtube", "streaming_audio", "api_polling"]
    config: Dict[str, Any] = Field(default_factory=dict)


class HttpBrowserConfig(BaseModel):
    """HTTP browser traffic configuration"""
    urls: List[str] = Field(default_factory=lambda: ["http://httpbin.org/html"])
    interval: int = Field(default=30, description="Seconds between requests")
    timeout: int = Field(default=10, description="Request timeout in seconds")
    user_agent: Optional[str] = None


class VideoStreamConfig(BaseModel):
    """Video streaming traffic configuration"""
    bandwidth: str = Field(default="5mbps", description="Target bandwidth (e.g., '5mbps', '1mbps')")
    duration: Optional[int] = Field(default=None, description="Duration in seconds, None for continuous")
    url: Optional[str] = Field(default=None, description="Streaming URL or generate synthetic")


class BulkTransferConfig(BaseModel):
    """Bulk transfer traffic configuration"""
    url: str = Field(description="URL to download/upload")
    direction: Literal["download", "upload"] = "download"
    repeat: bool = Field(default=False, description="Repeat transfer continuously")
    max_bandwidth: Optional[str] = Field(default=None, description="Max bandwidth limit")


class IdleConfig(BaseModel):
    """Idle traffic configuration"""
    keepalive_interval: int = Field(default=60, description="Keepalive ping interval in seconds")


class SpeedTestConfig(BaseModel):
    """Speed test traffic configuration"""
    service: Literal["fast", "speedtest", "both"] = Field(
        default="both",
        description="Speed test service: 'fast' (fast.com/Netflix), 'speedtest' (speedtest.net), or 'both'"
    )
    interval: int = Field(default=300, description="Seconds between speed tests")
    duration: int = Field(default=30, description="Seconds to run each test")


class YouTubeConfig(BaseModel):
    """YouTube streaming traffic configuration"""
    quality: Literal["auto", "360p", "480p", "720p", "1080p", "1440p", "4k"] = Field(
        default="auto",
        description="Video quality (auto = weighted random selection)"
    )
    watch_duration_min: int = Field(default=900, description="Minimum watch time in seconds (15 min)")
    watch_duration_max: int = Field(default=2700, description="Maximum watch time in seconds (45 min)")
    pause_between_min: int = Field(default=30, description="Minimum pause between videos (seconds)")
    pause_between_max: int = Field(default=300, description="Maximum pause between videos (seconds)")


# Interface Configuration Models
class InterfaceConfig(BaseModel):
    """Configuration for a single virtual interface"""
    name: str = Field(description="Interface name (e.g., wlan0_1)")
    ssid: str = Field(description="SSID to connect to")
    password: str = Field(description="Wi-Fi password")
    mac_address: Optional[str] = Field(default=None, description="MAC address (randomized if not specified)")
    traffic: Optional[TrafficConfig] = Field(default=None, description="Traffic configuration")
    dhcp_personality: Optional[str] = Field(
        default=None,
        description="Optional DHCP personality hint (e.g., 'windows10', 'linux', 'xbox')"
    )


class AgentConfiguration(BaseModel):
    """Complete agent configuration"""
    interfaces: List[InterfaceConfig] = Field(default_factory=list)


# Interface Status Models
class TrafficStatus(BaseModel):
    """Status of traffic generator for an interface"""
    type: str
    active: bool
    stats: Dict[str, Any] = Field(default_factory=dict)


class InterfaceStatus(BaseModel):
    """Status of a single interface"""
    name: str
    state: Literal["creating", "connecting", "connected", "disconnected", "error", "destroyed"]
    ssid: Optional[str] = None
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    signal_strength_dbm: Optional[float] = None
    tx_bytes: int = 0
    rx_bytes: int = 0
    tx_packets: int = 0
    rx_packets: int = 0
    error_message: Optional[str] = None
    traffic: Optional[TrafficStatus] = None
    dhcp_personality: Optional[str] = None  # DHCP personality used for this interface


class SystemStatus(BaseModel):
    """System-level status"""
    cpu_percent: float
    memory_percent: float
    temperature_celsius: Optional[float] = None
    uptime_seconds: float


class InterfaceCapability(BaseModel):
    """Capability information for a single wireless interface"""
    name: str = Field(description="Interface name (e.g., wlan0, wlan1)")
    max_interfaces: int = Field(description="Total managed interfaces supported (base + VIFs)")
    supports_vif: bool = Field(description="Whether virtual interface creation is supported")


class AgentStatus(BaseModel):
    """Complete agent status"""
    agent_id: str
    hostname: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    interfaces: List[InterfaceStatus] = Field(default_factory=list)
    system: SystemStatus
    capabilities: Dict[str, Any] = Field(
        default_factory=dict,
        description="Agent capabilities including all wireless interfaces and total capacity"
    )


# Pi Registration Models
class PiRegistration(BaseModel):
    """Pi registration request"""
    agent_id: str
    hostname: str
    ip_address: str
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    version: str = Field(default="1.0.0")


class PiInfo(BaseModel):
    """Pi information stored in controller"""
    pi_id: str
    agent_id: str
    hostname: str
    ip_address: str
    capabilities: Dict[str, Any]
    version: str
    last_seen: datetime
    status: Literal["online", "offline", "error"]


# Scenario Models
class PiInterfaceAssignment(BaseModel):
    """Interface assignment for a Pi in a scenario"""
    name: str
    ssid: str
    password: Optional[str] = None
    psk_set_id: Optional[str] = Field(
        default=None,
        description="Optional reference to a PSK set managed by the controller"
    )
    psk_index: Optional[int] = Field(
        default=None,
        description="Optional index into PSK set for deterministic assignment"
    )
    mac_address: Optional[str] = None
    traffic: Optional[TrafficConfig] = None
    dhcp_personality: Optional[str] = Field(
        default=None,
        description="Optional DHCP personality hint (e.g., 'windows10', 'linux', 'xbox')"
    )


class PiAssignment(BaseModel):
    """Pi assignment in a scenario"""
    pi_id: str
    interfaces: List[PiInterfaceAssignment]


class Scenario(BaseModel):
    """Complete scenario definition"""
    id: Optional[str] = None
    name: str
    description: str = ""
    pis: List[PiAssignment] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ScenarioStatus(BaseModel):
    """Status of an applied scenario"""
    scenario_id: str
    scenario_name: str
    state: Literal["applying", "running", "stopping", "stopped", "error"]
    started_at: Optional[datetime] = None
    pi_statuses: Dict[str, AgentStatus] = Field(default_factory=dict)
    total_interfaces: int = 0
    connected_interfaces: int = 0
    error_message: Optional[str] = None


# API Response Models
class SuccessResponse(BaseModel):
    """Generic success response"""
    success: bool = True
    message: str = "Operation completed successfully"
    data: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Generic error response"""
    success: bool = False
    error: str
    details: Optional[Dict[str, Any]] = None


# Orchestration Models
class ApplyScenarioRequest(BaseModel):
    """Request to apply a scenario"""
    scenario_id: str
    auto_start: bool = Field(default=True, description="Automatically start traffic after connecting")


class StopScenarioRequest(BaseModel):
    """Request to stop a scenario"""
    scenario_id: str
    cleanup: bool = Field(default=True, description="Destroy all interfaces")
