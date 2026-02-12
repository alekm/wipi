"""
WiPi Controller - Main FastAPI application entry point.

Central controller for managing the Pi fleet and coordinating scenarios.
"""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from controller.src.db import init_db, SessionLocal, engine
from controller.src.services import (
    PiManager,
    ScenarioManager,
    Orchestrator,
    MonitoringService,
    PskManager,
    ResidentSimulator,
    DesiredConfigManager,
)
from controller.src.api import pis, scenarios, orchestration, psk_sets, resident_simulation, ruckus_one, configuration, auth
from controller.src.limiter import limiter

# Configure logging (LOG_FORMAT=json for structured output)
def _configure_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    if os.environ.get("LOG_FORMAT", "").lower() == "json":
        try:
            from pythonjsonlogger import jsonlogger
            handler.setFormatter(jsonlogger.JsonFormatter())
        except ImportError:
            handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    if root.handlers:
        root.handlers.clear()
    root.addHandler(handler)

_configure_logging()
logger = logging.getLogger(__name__)

# Enable DEBUG logging for monitoring service
logging.getLogger('controller.src.services.monitoring').setLevel(logging.DEBUG)


# Global configuration
class Config:
    """Controller configuration"""
    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///./data/wipi.db")
    scenario_dir: str = os.environ.get("SCENARIO_DIR", "./scenarios")
    poll_interval_seconds: int = int(os.environ.get("POLL_INTERVAL_SECONDS", "10"))
    pi_timeout_seconds: int = int(os.environ.get("PI_TIMEOUT_SECONDS", "30"))
    config_file: str = os.environ.get("CONFIG_FILE", "./controller/config/default_config.yaml")

    # Timeout configurations (in seconds)
    orchestrator_configure_timeout: int = int(os.environ.get("ORCHESTRATOR_CONFIGURE_TIMEOUT", "10"))
    orchestrator_apply_timeout: int = int(os.environ.get("ORCHESTRATOR_APPLY_TIMEOUT", "120"))
    orchestrator_stop_timeout: int = int(os.environ.get("ORCHESTRATOR_STOP_TIMEOUT", "30"))
    orchestrator_status_timeout: int = int(os.environ.get("ORCHESTRATOR_STATUS_TIMEOUT", "5"))
    monitoring_poll_timeout: int = int(os.environ.get("MONITORING_POLL_TIMEOUT", "5"))
    ruckus_one_api_timeout: int = int(os.environ.get("RUCKUS_ONE_API_TIMEOUT", "10"))

    # Security configurations
    agent_api_key: str = os.environ.get("AGENT_API_KEY", "387d5f76c069bc167dc3ba74b1adb2b25233e9874e369dfa436894c3906bad0e")
    session_cookie_secure: bool = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"

    @classmethod
    def load_from_file(cls):
        """Load configuration from file if it exists"""
        try:
            if os.path.exists(cls.config_file):
                with open(cls.config_file, 'r') as f:
                    config_data = yaml.safe_load(f)
                    if config_data:
                        cls.database_url = config_data.get("database_url", cls.database_url)
                        cls.scenario_dir = config_data.get("scenario_dir", cls.scenario_dir)
                        cls.poll_interval_seconds = config_data.get("poll_interval_seconds", cls.poll_interval_seconds)
                        cls.pi_timeout_seconds = config_data.get("pi_timeout_seconds", cls.pi_timeout_seconds)

                        # Load timeout configurations
                        cls.orchestrator_configure_timeout = config_data.get("orchestrator_configure_timeout", cls.orchestrator_configure_timeout)
                        cls.orchestrator_apply_timeout = config_data.get("orchestrator_apply_timeout", cls.orchestrator_apply_timeout)
                        cls.orchestrator_stop_timeout = config_data.get("orchestrator_stop_timeout", cls.orchestrator_stop_timeout)
                        cls.orchestrator_status_timeout = config_data.get("orchestrator_status_timeout", cls.orchestrator_status_timeout)
                        cls.monitoring_poll_timeout = config_data.get("monitoring_poll_timeout", cls.monitoring_poll_timeout)
                        cls.ruckus_one_api_timeout = config_data.get("ruckus_one_api_timeout", cls.ruckus_one_api_timeout)

                        logger.info(f"Loaded configuration from {cls.config_file}")
        except Exception as e:
            logger.warning(f"Could not load config file: {e}")


def _get_cors_origins() -> list:
    """Parse CORS_ORIGINS env var. Default '*' allows all origins."""
    raw = os.environ.get("CORS_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app.
    Handles startup and shutdown logic.
    """
    # Load configuration
    Config.load_from_file()

    logger.info("Starting WiPi Controller")

    # SECURITY WARNINGS for default credentials
    if Config.agent_api_key == "387d5f76c069bc167dc3ba74b1adb2b25233e9874e369dfa436894c3906bad0e":
        logger.warning("=" * 80)
        logger.warning("SECURITY WARNING: Using default AGENT_API_KEY!")
        logger.warning("Generate a new key with: openssl rand -hex 32")
        logger.warning("Set AGENT_API_KEY in .env or docker-compose.yml")
        logger.warning("=" * 80)

    # Check admin password hash
    from .api.auth import is_using_default_password
    if is_using_default_password():
        logger.warning("=" * 80)
        logger.warning("SECURITY WARNING: Using default admin password!")
        logger.warning("Default password is 'Ruckus123!' - change immediately!")
        logger.warning("Run: ./scripts/wipi-init  (regenerates credentials with bcrypt)")
        logger.warning("Or set WIPI_ADMIN_PASSWORD_HASH in .env or docker-compose.yml")
        logger.warning("=" * 80)

    logger.info(f"Database URL: {Config.database_url}")
    logger.info(f"Scenario directory: {Config.scenario_dir}")

    # Initialize database
    logger.info("Initializing database")
    init_db()

    # Initialize services
    pi_manager = PiManager()
    pi_manager.pi_timeout_seconds = Config.pi_timeout_seconds

    scenario_manager = ScenarioManager(scenario_dir=Config.scenario_dir)
    psk_manager = PskManager()
    desired_config_manager = DesiredConfigManager()

    orchestrator = Orchestrator(pi_manager, scenario_manager, psk_manager, config=Config, desired_config_manager=desired_config_manager)
    resident_simulator = ResidentSimulator(
        pi_manager=pi_manager,
        scenario_manager=scenario_manager,
        psk_manager=psk_manager,
        orchestrator=orchestrator,
        db_session_maker=SessionLocal,
    )

    monitoring = MonitoringService(
        pi_manager,
        poll_interval=Config.poll_interval_seconds,
        poll_timeout=Config.monitoring_poll_timeout
    )

    # Store services in app state
    app.state.pi_manager = pi_manager
    app.state.scenario_manager = scenario_manager
    app.state.psk_manager = psk_manager
    app.state.desired_config_manager = desired_config_manager
    app.state.orchestrator = orchestrator
    app.state.monitoring = monitoring
    app.state.resident_simulator = resident_simulator

    # Load scenarios from directory
    logger.info("Loading scenarios from directory")
    db = SessionLocal()
    try:
        count = scenario_manager.load_scenarios_from_directory(db)
        logger.info(f"Loaded {count} scenarios")
    finally:
        db.close()

    # Start monitoring service
    logger.info("Starting monitoring service")
    await monitoring.start(SessionLocal)

    # Start resident simulator if it was enabled (auto-recover after restart)
    if resident_simulator.config.enabled:
        logger.info("Auto-starting resident simulator (config enabled)")
        await resident_simulator.start()

    logger.info("WiPi Controller started successfully")

    yield

    # Shutdown
    logger.info("Shutting down WiPi Controller")

    # Stop monitoring service
    await monitoring.stop()

    logger.info("WiPi Controller shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="WiPi Controller",
    description="Wi-Fi Client Farm Controller - Central orchestration for Pi fleet",
    version="1.0.0",
    lifespan=lifespan
)

# Add rate limiter to app state
app.state.limiter = limiter

# Add rate limit exceeded exception handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware (CORS_ORIGINS env: * = allow all, or comma-separated origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add SlowAPI middleware for rate limiting
app.add_middleware(SlowAPIMiddleware)

# Include routers
app.include_router(auth.router)
app.include_router(pis.router)
app.include_router(scenarios.router)
app.include_router(orchestration.router)
app.include_router(psk_sets.router)
app.include_router(resident_simulation.router)
app.include_router(ruckus_one.router, prefix="/api/ruckus_one", tags=["Ruckus One"])
app.include_router(configuration.router)


@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {
        "service": "WiPi Controller",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint - basic liveness."""
    return {"status": "healthy"}


@app.get("/health/ready")
async def health_ready():
    """
    Readiness check - verifies DB connectivity.
    Use for Docker/k8s health probes; returns 503 if DB unreachable.
    """
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "error", "detail": str(e)}
        )


if __name__ == "__main__":
    import uvicorn

    # Ensure data directory exists
    os.makedirs("./data", exist_ok=True)

    # Run the server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
