"""Payload models per EventCategory (docs/07 §1.2).

Each model is a `BaseModel` with `extra="allow"` so simulators may attach
scenario-specific fields (e.g., `sqli_pattern` on http requests) while
guaranteeing the required carrier fields are present. Phase 1 keeps the
required-field set minimal; Phase 2 simulators will tighten what's required.

Categories live one per module (docs/21 Task 1.1):
  http · database · auth · api · network · host · package · process · system
"""

from cybersim.events.payloads.api import (
    APIAuthzPayload,
    APIDataResponsePayload,
    APIRateWindowPayload,
    APIRequestPayload,
)
from cybersim.events.payloads.auth import (
    AuthAttemptPayload,
    AuthSuccessPayload,
    SessionCreatedPayload,
)
from cybersim.events.payloads.database import DBErrorPayload, DBQueryPayload
from cybersim.events.payloads.host import (
    HostLoginAttemptPayload,
    HostProcessSpawnPayload,
    HostSessionPayload,
    NetLateralHopPayload,
)
from cybersim.events.payloads.http import HTTPErrorPayload, HTTPRequestPayload
from cybersim.events.payloads.network import (
    NetConnectionPayload,
    NetScanProbePayload,
    NetServiceDiscoveredPayload,
)
from cybersim.events.payloads.package import (
    BuildDependencyResolvePayload,
    PackageInstalledPayload,
    PackageLifecycleHookPayload,
)
from cybersim.events.payloads.process import (
    ProcessEnvExfilPayload,
    ProcessExecPayload,
)
from cybersim.events.payloads.system import ResponseAppliedPayload

__all__ = [
    "APIAuthzPayload",
    "APIDataResponsePayload",
    "APIRateWindowPayload",
    # api
    "APIRequestPayload",
    # auth
    "AuthAttemptPayload",
    "AuthSuccessPayload",
    # package
    "BuildDependencyResolvePayload",
    "DBErrorPayload",
    # database
    "DBQueryPayload",
    "HTTPErrorPayload",
    # http
    "HTTPRequestPayload",
    # host
    "HostLoginAttemptPayload",
    "HostProcessSpawnPayload",
    "HostSessionPayload",
    # network
    "NetConnectionPayload",
    "NetLateralHopPayload",
    "NetScanProbePayload",
    "NetServiceDiscoveredPayload",
    "PackageInstalledPayload",
    "PackageLifecycleHookPayload",
    "ProcessEnvExfilPayload",
    # process
    "ProcessExecPayload",
    # system
    "ResponseAppliedPayload",
    "SessionCreatedPayload",
]
