"""Linux integration: platform boundary for resource control."""

from arc.linux.capabilities import PlatformCapabilities, detect_capabilities
from arc.linux.cgroups import (
    CgroupCapabilities,
    CgroupLease,
    CgroupManager,
    FakeCgroupManager,
    LinuxCgroupManager,
)
from arc.linux.fake_adapter import FakeProcess, FakeResourceAdapter
from arc.linux.psutil_adapter import LinuxResourceAdapter
from arc.linux.resources import (
    CgroupUnavailableError,
    InvalidCpusError,
    ProcessIdentity,
    ProcessNotFoundError,
    ResourceAdapter,
    ResourceControlError,
    ResourcePermissionError,
    ResourceSnapshot,
    StaleProcessError,
    UnsupportedActionError,
    UnsupportedPlatformError,
)

__all__ = [
    "CgroupCapabilities",
    "CgroupLease",
    "CgroupManager",
    "CgroupUnavailableError",
    "FakeCgroupManager",
    "FakeProcess",
    "FakeResourceAdapter",
    "InvalidCpusError",
    "LinuxCgroupManager",
    "LinuxResourceAdapter",
    "PlatformCapabilities",
    "ProcessIdentity",
    "ProcessNotFoundError",
    "ResourceAdapter",
    "ResourceControlError",
    "ResourcePermissionError",
    "ResourceSnapshot",
    "StaleProcessError",
    "UnsupportedActionError",
    "UnsupportedPlatformError",
    "detect_capabilities",
]
