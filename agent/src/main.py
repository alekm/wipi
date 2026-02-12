"""
WiPi Agent - Main FastAPI application entry point.

This agent runs on each Raspberry Pi and provides API endpoints for:
- Configuration management
- Interface control
- Traffic generation
- Status reporting
"""
import asyncio
import logging
import os
import sys
import socket
from contextlib import asynccontextmanager
from typing import Any, Optional
from urllib.parse import urlparse

import aiohttp
import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.models import PiRegistration

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from agent.src.core import (
    InterfaceManager,
    WPAManager,
    DHCPManager,
    ProcessManager,
    TrafficManager
)
from agent.src.monitoring import MetricsCollector
from agent.src.services.config_store import ConfigStore
from agent.src.services.config_pull import ConfigPullService
from agent.src.services.captive_portal_checker import CaptivePortalChecker
from agent.src.api import configure, apply, status

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Global configuration
class Config:
    """Agent configuration"""
    agent_id: str = os.environ.get("AGENT_ID", socket.gethostname())
    controller_url: str = os.environ.get("CONTROLLER_URL", "http://localhost:8000")
    agent_api_key: str = os.environ.get("AGENT_API_KEY", "387d5f76c069bc167dc3ba74b1adb2b25233e9874e369dfa436894c3906bad0e")
    api_port: int = int(os.environ.get("API_PORT", "8080"))
    max_interfaces: int = int(os.environ.get("MAX_INTERFACES", "8"))
    base_interface: str = os.environ.get("BASE_INTERFACE", "wlan0")
    dhcp_client: str = os.environ.get("DHCP_CLIENT", "dhclient")
    mock_mode: bool = os.environ.get("MOCK_MODE", "false").lower() == "true"
    config_file: str = os.environ.get("CONFIG_FILE", "/etc/wipi/agent_config.yaml")

    # VIF support flag (disabled by default due to Pi 4B routing issues)
    # Set to true for Pi 5 hardware or when VIF routing is fixed
    enable_vif: bool = os.environ.get("ENABLE_VIF", "false").lower() == "true"

    # Timeout configurations (in seconds)
    wpa_connection_timeout: int = int(os.environ.get("WPA_CONNECTION_TIMEOUT", "30"))
    wpa_process_timeout: int = int(os.environ.get("WPA_PROCESS_TIMEOUT", "5"))
    dhcp_ip_timeout: int = int(os.environ.get("DHCP_IP_TIMEOUT", "30"))
    dhcp_process_timeout: int = int(os.environ.get("DHCP_PROCESS_TIMEOUT", "5"))
    captive_portal_timeout: int = int(os.environ.get("CAPTIVE_PORTAL_TIMEOUT", "10"))
    registration_timeout: int = int(os.environ.get("REGISTRATION_TIMEOUT", "5"))
    bulk_transfer_timeout: int = int(os.environ.get("BULK_TRANSFER_TIMEOUT", "300"))
    youtube_timeout: int = int(os.environ.get("YOUTUBE_TIMEOUT", "30"))
    speedtest_timeout: int = int(os.environ.get("SPEEDTEST_TIMEOUT", "60"))
    speedtest_ping_timeout: int = int(os.environ.get("SPEEDTEST_PING_TIMEOUT", "10"))
    config_pull_interval: int = int(os.environ.get("CONFIG_PULL_INTERVAL", "30"))

    @classmethod
    def load_from_file(cls):
        """Load configuration from file if it exists"""
        try:
            if os.path.exists(cls.config_file):
                with open(cls.config_file, 'r') as f:
                    config_data = yaml.safe_load(f)
                    if config_data:
                        cls.agent_id = config_data.get("agent_id", cls.agent_id)
                        cls.controller_url = config_data.get("controller_url", cls.controller_url)
                        cls.agent_api_key = config_data.get("agent_api_key", cls.agent_api_key)
                        cls.api_port = config_data.get("api_port", cls.api_port)
                        cls.max_interfaces = config_data.get("max_interfaces", cls.max_interfaces)
                        cls.base_interface = config_data.get("default_base_interface", cls.base_interface)
                        cls.dhcp_client = config_data.get("dhcp_client", cls.dhcp_client)
                        cls.mock_mode = config_data.get("mock_mode", cls.mock_mode)
                        cls.enable_vif = config_data.get("enable_vif", cls.enable_vif)

                        # Load timeout configurations
                        cls.wpa_connection_timeout = config_data.get("wpa_connection_timeout", cls.wpa_connection_timeout)
                        cls.wpa_process_timeout = config_data.get("wpa_process_timeout", cls.wpa_process_timeout)
                        cls.dhcp_ip_timeout = config_data.get("dhcp_ip_timeout", cls.dhcp_ip_timeout)
                        cls.dhcp_process_timeout = config_data.get("dhcp_process_timeout", cls.dhcp_process_timeout)
                        cls.captive_portal_timeout = config_data.get("captive_portal_timeout", cls.captive_portal_timeout)
                        cls.registration_timeout = config_data.get("registration_timeout", cls.registration_timeout)
                        cls.bulk_transfer_timeout = config_data.get("bulk_transfer_timeout", cls.bulk_transfer_timeout)
                        cls.youtube_timeout = config_data.get("youtube_timeout", cls.youtube_timeout)
                        cls.speedtest_timeout = config_data.get("speedtest_timeout", cls.speedtest_timeout)
                        cls.speedtest_ping_timeout = config_data.get("speedtest_ping_timeout", cls.speedtest_ping_timeout)
                        cls.config_pull_interval = config_data.get("config_pull_interval", cls.config_pull_interval)

                        logger.info(f"Loaded configuration from {cls.config_file}")
        except Exception as e:
            logger.warning(f"Could not load config file: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app.
    Handles startup and shutdown logic.
    """
    # Load configuration
    Config.load_from_file()

    logger.info(f"Starting WiPi Agent: {Config.agent_id}")
    logger.info(f"Mock mode: {Config.mock_mode}")
    logger.info(f"Base interface: {Config.base_interface}")
    logger.info(f"Controller URL: {Config.controller_url}")

    # Initialize managers
    interface_manager = InterfaceManager(
        base_interface=Config.base_interface,
        mock_mode=Config.mock_mode,
        config=Config
    )
    wpa_manager = WPAManager(mock_mode=Config.mock_mode, config=Config)
    dhcp_manager = DHCPManager(
        dhcp_client=Config.dhcp_client,
        mock_mode=Config.mock_mode,
        config=Config
    )
    process_manager = ProcessManager(mock_mode=Config.mock_mode)
    traffic_manager = TrafficManager(mock_mode=Config.mock_mode, config=Config)
    metrics_collector = MetricsCollector(mock_mode=Config.mock_mode)

    # Start process manager
    await process_manager.start()

    # Store managers in app state
    app.state.agent_id = Config.agent_id
    app.state.interface_manager = interface_manager
    app.state.wpa_manager = wpa_manager
    app.state.dhcp_manager = dhcp_manager
    app.state.process_manager = process_manager
    app.state.traffic_manager = traffic_manager
    app.state.metrics_collector = metrics_collector

    # Initialize config pull service for autonomous configuration updates
    config_store = ConfigStore()

    async def apply_config_callback(agent_config):
        """Callback for config pull service to apply configuration"""
        from agent.src.api.apply import apply_configuration_internal
        await apply_configuration_internal(
            agent_config,
            interface_manager,
            wpa_manager,
            dhcp_manager,
            traffic_manager,
            Config
        )

    config_pull_service = ConfigPullService(
        agent_id=Config.agent_id,
        controller_url=Config.controller_url,
        config_store=config_store,
        apply_callback=apply_config_callback,
        agent_api_key=Config.agent_api_key,
        poll_interval=Config.config_pull_interval,
        interface_manager=interface_manager,
        wpa_manager=wpa_manager
    )

    # Initialize captive portal checker (runs for all interfaces to ensure User-Agent visibility)
    captive_portal_checker = CaptivePortalChecker(
        interface_manager=interface_manager,
        dhcp_manager=dhcp_manager,
        check_interval=45,  # Check every 45 seconds
        timeout=5
    )

    app.state.config_store = config_store
    app.state.config_pull_service = config_pull_service
    app.state.captive_portal_checker = captive_portal_checker

    logger.info("WiPi Agent started successfully")

    # Start background registration loop (call-home to controller)
    app.state._register_task = asyncio.create_task(_register_with_controller_loop())

    # Start config pull service and captive portal checker
    if not Config.mock_mode:
        await config_pull_service.start()

        # Try to recover persisted config on startup
        logger.info("Attempting to recover persisted configuration...")
        await config_pull_service.recover_config_on_startup()

        # Start captive portal checker
        await captive_portal_checker.start()
    else:
        logger.info("Mock mode enabled; skipping config pull service and captive portal checker")

    yield

    # Shutdown
    logger.info("Shutting down WiPi Agent")

    # Stop all traffic
    await traffic_manager.stop_all_traffic()

    # Stop all DHCP clients
    await dhcp_manager.stop_all()

    # Stop all wpa_supplicant processes
    await wpa_manager.stop_all()

    # Destroy all interfaces
    await interface_manager.destroy_all_interfaces()

    # Stop process manager
    await process_manager.stop()

    # Stop registration loop
    register_task: Optional[asyncio.Task] = getattr(app.state, "_register_task", None)
    if register_task:
        register_task.cancel()
        try:
            await register_task
        except asyncio.CancelledError:
            pass

    # Stop config pull service
    config_pull_service = getattr(app.state, "config_pull_service", None)
    if config_pull_service:
        await config_pull_service.stop()

    # Stop captive portal checker
    captive_portal_checker = getattr(app.state, "captive_portal_checker", None)
    if captive_portal_checker:
        await captive_portal_checker.stop()

    logger.info("WiPi Agent shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="WiPi Agent",
    description="Wi-Fi Client Farm Agent - Manages virtual interfaces and traffic generation",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(configure.router, tags=["Configuration"])
app.include_router(apply.router, tags=["Configuration"])
app.include_router(status.router, tags=["Status"])


@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {
        "service": "WiPi Agent",
        "version": "1.0.0",
        "agent_id": Config.agent_id,
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "agent_id": Config.agent_id
    }


# Let uvicorn handle SIGTERM/SIGINT for clean asyncio shutdown (no custom handler)


async def _register_with_controller_loop() -> None:
    """
    Periodically register this agent with the controller so the controller
    learns/refreshes our IP address and capabilities.
    """
    if Config.mock_mode:
        logger.info("Mock mode enabled; skipping controller registration loop")
        return

    logger.info("Starting controller registration loop")

    while True:
        try:
            await _register_with_controller_once()
        except asyncio.CancelledError:
            logger.info("Controller registration loop cancelled")
            raise
        except Exception as e:
            logger.warning(f"Error in controller registration loop: {e}")

        # Refresh registration every 60 seconds
        await asyncio.sleep(60)


async def _register_with_controller_once() -> None:
    """Send a single registration request to the controller."""
    controller_url = Config.controller_url.rstrip("/")
    parsed = urlparse(controller_url)
    if not parsed.scheme or not parsed.netloc:
        logger.warning(f"Invalid CONTROLLER_URL '{Config.controller_url}', skipping registration")
        return

    api_base = f"{parsed.scheme}://{parsed.netloc}"
    url = f"{api_base}/api/pis/register"

    ip_address = _get_primary_ip(parsed.hostname or "8.8.8.8", parsed.port or 80)
    if not ip_address:
        logger.warning("Could not determine primary IP address, skipping registration")
        return

    registration = PiRegistration(
        agent_id=Config.agent_id,
        hostname=socket.gethostname(),
        ip_address=ip_address,
        capabilities={
            "max_interfaces": Config.max_interfaces,
            "base_interface": Config.base_interface,
        },
        version="1.0.0",
    )

    try:
        timeout = aiohttp.ClientTimeout(total=Config.registration_timeout)
        headers = {"X-Agent-Api-Key": Config.agent_api_key}
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=registration.model_dump(), headers=headers) as resp:
                if resp.status == 200:
                    logger.info(
                        "Registered with controller at %s (agent_id=%s, ip=%s)",
                        url,
                        Config.agent_id,
                        ip_address,
                    )
                else:
                    text = await resp.text()
                    logger.warning(
                        "Controller registration failed: HTTP %s - %s",
                        resp.status,
                        text,
                    )
    except Exception as e:
        logger.warning(f"Error registering with controller at {url}: {e}")


def _get_primary_ip(dest_host: str, dest_port: int) -> Optional[str]:
    """
    Determine the primary IP address used to reach dest_host/dest_port.
    This avoids hard-coding interface names and works with DHCP.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
        sock.connect((dest_host, dest_port))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception as e:
        logger.warning(f"Failed to determine primary IP via UDP socket: {e}")
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception as e2:
            logger.warning(f"Fallback IP detection failed: {e2}")
            return None


if __name__ == "__main__":
    import uvicorn

    # Run the server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=Config.api_port,
        log_level="info"
    )
