"""
Apply endpoint - Apply the stored configuration.
"""
import asyncio
import logging
import random
from fastapi import APIRouter, HTTPException, Request
from shared.models import SuccessResponse
from ..core.mac_oui import get_mac_for_personality
from ..core.user_agents import get_user_agent_for_personality
from . import configure

logger = logging.getLogger(__name__)

router = APIRouter()


async def apply_configuration_internal(
    agent_config,
    interface_manager,
    wpa_manager,
    dhcp_manager,
    traffic_manager,
    config
):
    """
    Internal function to apply agent configuration.
    Can be called by both the API endpoint and the config pull service.

    Args:
        agent_config: AgentConfiguration object
        interface_manager: InterfaceManager instance
        wpa_manager: WPAManager instance
        dhcp_manager: DHCPManager instance
        traffic_manager: TrafficManager instance
        config: Config class with timeout settings

    Returns:
        dict with success, message, and data
    """
    # Store the configuration first
    configure.stored_configuration = agent_config

    logger.info(f"Applying configuration with {len(agent_config.interfaces)} interfaces")

    # Step 1: Destroy all existing interfaces
    logger.info("Step 1: Destroying existing interfaces")
    await traffic_manager.stop_all_traffic()
    await dhcp_manager.stop_all()
    await wpa_manager.stop_all()
    await interface_manager.destroy_all_interfaces()

    # If no interfaces configured, we're done
    if not agent_config.interfaces:
        logger.info("No interfaces to configure, cleanup complete")
        return {
            "success": True,
            "message": "Configuration applied (no interfaces)",
            "interfaces_configured": 0
        }

    # Define interface configuration function for parallel execution
    async def _configure_single_interface(iface_config):
        """Configure a single interface (runs in parallel with others)"""
        try:
            logger.info(f"Configuring interface: {iface_config.name}")

            # Step 2: Create interface
            # Generate MAC address with appropriate vendor OUI if not specified
            mac_address = iface_config.mac_address
            if not mac_address and iface_config.dhcp_personality:
                mac_address = get_mac_for_personality(iface_config.dhcp_personality)
                logger.info(f"  Generated {iface_config.dhcp_personality} MAC: {mac_address}")

            logger.info(f"  Creating interface {iface_config.name}")
            success = await interface_manager.create_interface(
                iface_config.name,
                mac_address
            )
            if not success:
                raise Exception(f"Failed to create interface {iface_config.name}")

            # Step 3: Start wpa_supplicant
            logger.info(f"  Starting wpa_supplicant for {iface_config.name}")
            success = await wpa_manager.start_wpa_supplicant(
                iface_config.name,
                iface_config.ssid,
                iface_config.password
            )
            if not success:
                raise Exception(f"Failed to start wpa_supplicant for {iface_config.name}")

            # Give wpa_supplicant time to create control socket before wpa_cli polls
            await asyncio.sleep(2)

            # Step 4: Wait for connection
            logger.info(f"  Waiting for {iface_config.name} to connect")
            connected = await wpa_manager.wait_for_connection(iface_config.name, timeout=config.wpa_connection_timeout)
            if not connected:
                logger.warning(f"  Interface {iface_config.name} failed to connect, continuing anyway")

            # Step 5: Start DHCP client with fingerprinting
            # Use DHCP personality if specified, otherwise generate random hostname
            personality = iface_config.dhcp_personality
            hostname = None  # Let profile generate hostname unless overridden

            if not personality:
                # No personality specified, generate random device hostname
                hostname = _generate_device_hostname()

            logger.info(
                f"  Starting DHCP for {iface_config.name}" +
                (f" as {personality}" if personality else f" with hostname {hostname}")
            )

            success = await dhcp_manager.start_dhcp(
                iface_config.name,
                hostname=hostname,
                personality=personality
            )
            if not success:
                raise Exception(f"Failed to start DHCP for {iface_config.name}")

            # Step 6: Wait for IP address
            logger.info(f"  Waiting for {iface_config.name} to get IP")
            ip_address = await dhcp_manager.wait_for_ip(iface_config.name, timeout=config.dhcp_ip_timeout)
            if not ip_address:
                logger.warning(f"  Interface {iface_config.name} failed to get IP, continuing anyway")

            # Step 6.5: Apple captive portal detection (if Apple personality)
            if iface_config.dhcp_personality and iface_config.dhcp_personality.lower() in ["iphone", "ipad", "macos", "macbook"]:
                logger.info(f"  Performing Apple captive portal check for {iface_config.name}")
                try:
                    import aiohttp
                    user_agent = get_user_agent_for_personality(iface_config.dhcp_personality)
                    headers = {"User-Agent": user_agent}
                    timeout = aiohttp.ClientTimeout(total=config.captive_portal_timeout)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get("http://captive.apple.com/hotspot-detect.html", headers=headers) as response:
                            content = await response.text()
                            if "Success" in content:
                                logger.info(f"  ✓ Apple captive portal check successful for {iface_config.name}")
                            else:
                                logger.warning(f"  Apple captive portal check got unexpected response for {iface_config.name}")
                except Exception as e:
                    logger.warning(f"  Apple captive portal check failed for {iface_config.name}: {e}")

            # Step 7: Start traffic generator (if configured)
            if iface_config.traffic:
                logger.info(
                    f"  Starting {iface_config.traffic.type} traffic for {iface_config.name}"
                )

                # Inject appropriate User-Agent based on DHCP personality
                traffic_config = dict(iface_config.traffic.config)
                if "user_agent" not in traffic_config and iface_config.dhcp_personality:
                    user_agent = get_user_agent_for_personality(iface_config.dhcp_personality)
                    traffic_config["user_agent"] = user_agent
                    logger.info(f"  Injected User-Agent for {iface_config.dhcp_personality}")

                # Add Apple-specific URLs for http_browser traffic
                if (iface_config.traffic.type == "http_browser" and
                    iface_config.dhcp_personality and
                    iface_config.dhcp_personality.lower() in ["iphone", "ipad", "macos", "macbook"]):
                    apple_urls = [
                        "http://captive.apple.com/hotspot-detect.html",
                        "http://www.apple.com",
                        "https://www.icloud.com",
                    ]
                    if "urls" not in traffic_config:
                        traffic_config["urls"] = apple_urls
                    else:
                        # Prepend Apple URLs to existing URLs
                        existing_urls = traffic_config["urls"]
                        traffic_config["urls"] = apple_urls + existing_urls
                    logger.info(f"  Added Apple-specific URLs to traffic for {iface_config.name}")

                success = await traffic_manager.start_traffic(
                    iface_config.name,
                    iface_config.traffic.type,
                    traffic_config
                )
                if not success:
                    logger.warning(
                        f"  Failed to start traffic for {iface_config.name}, continuing"
                    )

            logger.info(f"Successfully configured interface: {iface_config.name}")
            return {"success": True, "name": iface_config.name}

        except Exception as e:
            logger.error(f"Error configuring interface {iface_config.name}: {e}")
            return {"success": False, "name": iface_config.name, "error": str(e)}

    # Step 2-7: Configure all interfaces IN PARALLEL
    logger.info(f"Configuring {len(agent_config.interfaces)} interfaces in parallel")
    tasks = [_configure_single_interface(iface) for iface in agent_config.interfaces]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Count successes and failures
    configured_count = 0
    failed_interfaces = []

    for result in results:
        if isinstance(result, Exception):
            # Unexpected exception during gather
            failed_interfaces.append({
                "name": "unknown",
                "error": str(result)
            })
        elif result.get("success"):
            configured_count += 1
        else:
            failed_interfaces.append({
                "name": result.get("name", "unknown"),
                "error": result.get("error", "Unknown error")
            })

    # Return summary
    message = f"Configuration applied: {configured_count}/{len(agent_config.interfaces)} interfaces"
    if failed_interfaces:
        message += f", {len(failed_interfaces)} failed"

    logger.info(message)

    return {
        "success": configured_count > 0 or len(agent_config.interfaces) == 0,
        "message": message,
        "interfaces_configured": configured_count,
        "interfaces_failed": len(failed_interfaces),
        "failed_interfaces": failed_interfaces,
    }


def _generate_device_hostname() -> str:
    """Generate a realistic device hostname for DHCP requests."""
    device_types = [
        ("iPhone", lambda: f"iPhone-{random.randint(1000, 9999)}"),
        ("iPad", lambda: f"iPad-{random.randint(1000, 9999)}"),
        ("MacBook", lambda: f"MacBook-{random.choice(['Pro', 'Air'])}-{random.randint(100, 999)}"),
        ("Samsung", lambda: f"Samsung-{random.choice(['S21', 'S22', 'S23', 'A54'])}-{random.randint(100, 999)}"),
        ("Pixel", lambda: f"Pixel-{random.choice(['6', '7', '8'])}-{random.randint(100, 999)}"),
        ("DESKTOP", lambda: f"DESKTOP-{random.randint(10000, 99999)}"),
        ("laptop", lambda: f"laptop-{random.randint(1000, 9999)}"),
        ("Android", lambda: f"Android-{random.randint(1000, 9999)}"),
        ("Smart-TV", lambda: f"{random.choice(['Samsung', 'LG', 'Sony'])}-TV-{random.randint(100, 999)}"),
        ("Echo", lambda: f"Echo-{random.choice(['Dot', 'Show', 'Studio'])}-{random.randint(100, 999)}"),
    ]

    device_type, generator = random.choice(device_types)
    return generator()


@router.post("/apply", response_model=SuccessResponse)
async def apply_configuration(request: Request) -> SuccessResponse:
    """
    Apply the stored configuration.

    This will:
    1. Destroy existing interfaces
    2. Create new interfaces
    3. Start wpa_supplicant for each interface
    4. Wait for connection
    5. Start DHCP client
    6. Wait for IP address
    7. Start traffic generators

    Returns:
        Success response
    """
    # Import Config here to avoid circular import
    from ..main import Config

    try:
        # Get managers from app state
        interface_manager = request.app.state.interface_manager
        wpa_manager = request.app.state.wpa_manager
        dhcp_manager = request.app.state.dhcp_manager
        traffic_manager = request.app.state.traffic_manager

        current_config = configure.stored_configuration

        # Call internal function
        result = await apply_configuration_internal(
            current_config,
            interface_manager,
            wpa_manager,
            dhcp_manager,
            traffic_manager,
            Config
        )

        return SuccessResponse(
            success=result["success"],
            message=result["message"],
            data={
                "interfaces_configured": result["interfaces_configured"],
                "interfaces_failed": result.get("interfaces_failed", 0),
                "failed_interfaces": result.get("failed_interfaces", []),
            },
        )

    except Exception as e:
        logger.error(f"Error applying configuration: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply configuration: {str(e)}"
        )
