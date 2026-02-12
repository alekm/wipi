"""
Status endpoint - Get current status of all interfaces and system.
"""
import logging
import socket
from datetime import datetime
from fastapi import APIRouter, Request
from shared.models import AgentStatus, InterfaceStatus, SystemStatus, TrafficStatus
from . import configure

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status", response_model=AgentStatus)
async def get_status(request: Request) -> AgentStatus:
    """
    Get current status of the agent, all interfaces, and system metrics.

    Returns:
        Complete agent status including interfaces and system info
    """
    try:
        # Get managers from app state
        interface_manager = request.app.state.interface_manager
        wpa_manager = request.app.state.wpa_manager
        dhcp_manager = request.app.state.dhcp_manager
        traffic_manager = request.app.state.traffic_manager
        metrics_collector = request.app.state.metrics_collector

        # Get agent ID and hostname
        agent_id = getattr(request.app.state, 'agent_id', 'unknown')
        hostname = socket.gethostname()

        # Collect system metrics
        system_metrics = await metrics_collector.get_system_metrics()
        system_status = SystemStatus(**system_metrics)

        # Detect VIF capabilities for all wireless interfaces
        all_capabilities = await interface_manager.get_all_interface_capabilities()

        # Build capabilities structure
        interface_caps = []
        total_capacity = 0
        for iface_name, max_count in all_capabilities.items():
            interface_caps.append({
                "name": iface_name,
                "max_interfaces": max_count,
                "supports_vif": max_count > 1
            })
            total_capacity += max_count

        # Get API port from config
        from ..main import Config

        capabilities = {
            "api_port": Config.api_port,  # Agent API port for controller communication
            "interfaces": interface_caps,
            "total_capacity": total_capacity,
            # Legacy fields for backward compatibility
            "base_interface": interface_manager.base_interface,
            "max_interfaces": all_capabilities.get(interface_manager.base_interface, 1),
            "supports_vif": all_capabilities.get(interface_manager.base_interface, 1) > 1
        }

        # Collect interface statuses
        interface_statuses = []

        # Get all tracked interfaces
        tracked_interfaces = set(interface_manager.interfaces.keys())

        for iface_name in tracked_interfaces:
            try:
                iface_status = await _get_interface_status(
                    iface_name,
                    interface_manager,
                    wpa_manager,
                    dhcp_manager,
                    traffic_manager
                )
                interface_statuses.append(iface_status)

            except Exception as e:
                logger.error(f"Error getting status for interface {iface_name}: {e}")
                # Add error status
                interface_statuses.append(InterfaceStatus(
                    name=iface_name,
                    state="error",
                    error_message=str(e)
                ))

        # Build agent status
        agent_status = AgentStatus(
            agent_id=agent_id,
            hostname=hostname,
            timestamp=datetime.utcnow(),
            interfaces=interface_statuses,
            system=system_status,
            capabilities=capabilities
        )

        return agent_status

    except Exception as e:
        logger.error(f"Error getting agent status: {e}")
        # Return minimal error status
        return AgentStatus(
            agent_id="unknown",
            hostname=socket.gethostname(),
            timestamp=datetime.utcnow(),
            interfaces=[],
            system=SystemStatus(
                cpu_percent=0.0,
                memory_percent=0.0,
                temperature_celsius=None,
                uptime_seconds=0.0
            )
        )


async def _get_interface_status(
    iface_name: str,
    interface_manager,
    wpa_manager,
    dhcp_manager,
    traffic_manager
) -> InterfaceStatus:
    """
    Get status for a single interface.

    Args:
        iface_name: Interface name
        interface_manager: Interface manager instance
        wpa_manager: WPA manager instance
        dhcp_manager: DHCP manager instance
        traffic_manager: Traffic manager instance

    Returns:
        InterfaceStatus object
    """
    # Get basic interface info
    iface_info = interface_manager.interfaces.get(iface_name, {})
    mac_address = iface_info.get("mac")

    # Get connection status from wpa_supplicant
    wpa_status = await wpa_manager.get_connection_status(iface_name)
    if wpa_status and wpa_status.get("connected"):
        state = "connected"
        ssid = wpa_status.get("ssid")
    else:
        state = "disconnected"
        ssid = None

    # Get IP address
    ip_address = await dhcp_manager.get_ip_address(iface_name)

    # Get signal strength
    signal_strength = await interface_manager.get_signal_strength(iface_name)

    # Get network statistics
    stats = await interface_manager.get_interface_stats(iface_name)
    if stats:
        tx_bytes = stats.get("tx_bytes", 0)
        rx_bytes = stats.get("rx_bytes", 0)
        tx_packets = stats.get("tx_packets", 0)
        rx_packets = stats.get("rx_packets", 0)
    else:
        tx_bytes = rx_bytes = tx_packets = rx_packets = 0

    # Get traffic status
    traffic_status = None
    if traffic_manager.is_traffic_active(iface_name):
        traffic_stats = traffic_manager.get_traffic_status(iface_name)
        if traffic_stats:
            traffic_status = TrafficStatus(
                type=traffic_stats.get("type", "unknown"),
                active=traffic_stats.get("active", False),
                stats={k: v for k, v in traffic_stats.items() if k not in ["type", "active"]}
            )

    # Get DHCP personality from stored configuration
    dhcp_personality = None
    for iface_config in configure.stored_configuration.interfaces:
        if iface_config.name == iface_name:
            dhcp_personality = iface_config.dhcp_personality
            break

    return InterfaceStatus(
        name=iface_name,
        state=state,
        ssid=ssid,
        ip_address=ip_address,
        mac_address=mac_address,
        signal_strength_dbm=signal_strength,
        tx_bytes=tx_bytes,
        rx_bytes=rx_bytes,
        tx_packets=tx_packets,
        rx_packets=rx_packets,
        traffic=traffic_status,
        dhcp_personality=dhcp_personality
    )
