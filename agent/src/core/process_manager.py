"""
Process Manager - Manages subprocess lifecycle for traffic generators and monitoring.
"""
import asyncio
import logging
import signal
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ManagedProcess:
    """Represents a managed subprocess"""
    name: str
    process: Optional[asyncio.subprocess.Process]
    start_time: datetime
    restart_count: int = 0
    health_check: Optional[Callable] = None
    auto_restart: bool = True


class ProcessManager:
    """Manages subprocess lifecycle with health monitoring and auto-restart"""

    def __init__(self, mock_mode: bool = False):
        """
        Initialize process manager.

        Args:
            mock_mode: If True, simulate process management without actual processes
        """
        self.mock_mode = mock_mode
        self.processes: Dict[str, ManagedProcess] = {}
        self.monitoring_task: Optional[asyncio.Task] = None
        self.shutdown_event = asyncio.Event()

        logger.info(f"ProcessManager initialized with mock_mode: {mock_mode}")

    async def start(self) -> None:
        """Start the process manager and monitoring"""
        logger.info("Starting ProcessManager")
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())

    async def stop(self) -> None:
        """Stop the process manager and all processes"""
        logger.info("Stopping ProcessManager")
        self.shutdown_event.set()

        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        await self.stop_all_processes()

    async def register_process(
        self,
        name: str,
        process: Optional[asyncio.subprocess.Process],
        health_check: Optional[Callable] = None,
        auto_restart: bool = True
    ) -> None:
        """
        Register a process for management.

        Args:
            name: Unique process name
            process: The subprocess object (None for externally managed processes)
            health_check: Optional async function to check process health
            auto_restart: Whether to auto-restart on failure
        """
        if name in self.processes:
            logger.warning(f"Process {name} already registered, updating")

        self.processes[name] = ManagedProcess(
            name=name,
            process=process,
            start_time=datetime.utcnow(),
            health_check=health_check,
            auto_restart=auto_restart
        )

        logger.info(f"Registered process: {name}")

    async def unregister_process(self, name: str) -> None:
        """
        Unregister a process from management.

        Args:
            name: Process name
        """
        if name in self.processes:
            del self.processes[name]
            logger.info(f"Unregistered process: {name}")

    async def stop_process(self, name: str, timeout: int = 5) -> bool:
        """
        Stop a managed process gracefully.

        Args:
            name: Process name
            timeout: Seconds to wait before force killing

        Returns:
            True if stopped successfully, False otherwise
        """
        if name not in self.processes:
            logger.warning(f"Process {name} not registered")
            return False

        managed = self.processes[name]
        process = managed.process

        if not process:
            logger.info(f"Process {name} has no process object (externally managed)")
            await self.unregister_process(name)
            return True

        if self.mock_mode:
            logger.info(f"[MOCK] Would stop process: {name}")
            await self.unregister_process(name)
            return True

        try:
            logger.info(f"Stopping process: {name}")

            # Check if process is still running
            if process.returncode is not None:
                logger.info(f"Process {name} already terminated")
                await self.unregister_process(name)
                return True

            # Send SIGTERM for graceful shutdown
            process.terminate()

            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
                logger.info(f"Process {name} terminated gracefully")
            except asyncio.TimeoutError:
                # Force kill if timeout
                logger.warning(f"Process {name} did not terminate gracefully, force killing")
                process.kill()
                await process.wait()
                logger.info(f"Process {name} force killed")

            await self.unregister_process(name)
            return True

        except Exception as e:
            logger.error(f"Error stopping process {name}: {e}")
            return False

    async def stop_all_processes(self) -> None:
        """Stop all managed processes"""
        logger.info(f"Stopping all {len(self.processes)} processes")

        # Stop processes concurrently
        tasks = [self.stop_process(name) for name in list(self.processes.keys())]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def is_process_running(self, name: str) -> bool:
        """
        Check if a process is running.

        Args:
            name: Process name

        Returns:
            True if running, False otherwise
        """
        if name not in self.processes:
            return False

        if self.mock_mode:
            return True

        managed = self.processes[name]
        process = managed.process

        if not process:
            # Externally managed process, assume running if registered
            return True

        return process.returncode is None

    async def get_process_status(self, name: str) -> Optional[Dict]:
        """
        Get process status information.

        Args:
            name: Process name

        Returns:
            Dict with status info or None
        """
        if name not in self.processes:
            return None

        managed = self.processes[name]
        is_running = await self.is_process_running(name)

        status = {
            "name": name,
            "running": is_running,
            "start_time": managed.start_time.isoformat(),
            "restart_count": managed.restart_count,
            "auto_restart": managed.auto_restart,
        }

        if managed.process:
            status["pid"] = managed.process.pid if is_running else None
            status["returncode"] = managed.process.returncode

        return status

    async def get_all_status(self) -> Dict[str, Dict]:
        """Get status for all managed processes"""
        status = {}
        for name in self.processes:
            proc_status = await self.get_process_status(name)
            if proc_status:
                status[name] = proc_status
        return status

    async def restart_process(self, name: str, restart_callback: Optional[Callable] = None) -> bool:
        """
        Restart a process.

        Args:
            name: Process name
            restart_callback: Optional async function to call to restart the process

        Returns:
            True if restarted successfully, False otherwise
        """
        if name not in self.processes:
            logger.warning(f"Process {name} not registered")
            return False

        logger.info(f"Restarting process: {name}")

        managed = self.processes[name]
        managed.restart_count += 1

        # Stop the process
        await self.stop_process(name)

        # Call restart callback if provided
        if restart_callback:
            try:
                await restart_callback()
                logger.info(f"Process {name} restarted successfully")
                return True
            except Exception as e:
                logger.error(f"Error restarting process {name}: {e}")
                return False
        else:
            logger.warning(f"No restart callback provided for {name}")
            return False

    async def _monitoring_loop(self) -> None:
        """Background monitoring loop for process health"""
        logger.info("Process monitoring loop started")

        try:
            while not self.shutdown_event.is_set():
                await self._check_all_processes()
                await asyncio.sleep(5)  # Check every 5 seconds

        except asyncio.CancelledError:
            logger.info("Process monitoring loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")

    async def _check_all_processes(self) -> None:
        """Check health of all processes"""
        for name, managed in list(self.processes.items()):
            try:
                # Check if process died
                is_running = await self.is_process_running(name)

                if not is_running and managed.auto_restart:
                    logger.warning(f"Process {name} died, auto-restart not implemented")
                    # In a full implementation, you would call a restart callback here
                    # For now, just unregister
                    await self.unregister_process(name)

                # Run custom health check if provided
                if managed.health_check and is_running:
                    try:
                        healthy = await managed.health_check()
                        if not healthy:
                            logger.warning(f"Process {name} failed health check")
                            # Could trigger restart here
                    except Exception as e:
                        logger.error(f"Error running health check for {name}: {e}")

            except Exception as e:
                logger.error(f"Error checking process {name}: {e}")

    def __del__(self):
        """Cleanup on deletion"""
        if self.processes:
            logger.warning(f"ProcessManager deleted with {len(self.processes)} processes still registered")
