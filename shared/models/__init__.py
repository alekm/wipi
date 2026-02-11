"""Shared models package for WiPi"""
from .api_contract import (
    # Traffic configs
    TrafficConfig,
    HttpBrowserConfig,
    VideoStreamConfig,
    BulkTransferConfig,
    IdleConfig,
    # Interface configs
    InterfaceConfig,
    AgentConfiguration,
    # Status models
    TrafficStatus,
    InterfaceStatus,
    SystemStatus,
    AgentStatus,
    # Pi registration
    PiRegistration,
    PiInfo,
    # Scenarios
    PiInterfaceAssignment,
    PiAssignment,
    Scenario,
    ScenarioStatus,
    # Responses
    SuccessResponse,
    ErrorResponse,
    # Orchestration
    ApplyScenarioRequest,
    StopScenarioRequest,
)

__all__ = [
    "TrafficConfig",
    "HttpBrowserConfig",
    "VideoStreamConfig",
    "BulkTransferConfig",
    "IdleConfig",
    "InterfaceConfig",
    "AgentConfiguration",
    "TrafficStatus",
    "InterfaceStatus",
    "SystemStatus",
    "AgentStatus",
    "PiRegistration",
    "PiInfo",
    "PiInterfaceAssignment",
    "PiAssignment",
    "Scenario",
    "ScenarioStatus",
    "SuccessResponse",
    "ErrorResponse",
    "ApplyScenarioRequest",
    "StopScenarioRequest",
]
