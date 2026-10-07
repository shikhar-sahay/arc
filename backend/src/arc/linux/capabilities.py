"""Platform and privilege reporting for enforcement decisions.

ARC never escalates privilege. This module only reports what the
platform likely allows so failures are explainable: enforcement needs
Linux, and some operations (lowering a nice value, touching another
user's process) need ownership or capabilities. UID 0 is sufficient in
most setups but it is not the only way capabilities can be granted
(file capabilities and delegated cgroups also exist), so the indicator
is a hint, not a verdict.
"""

import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformCapabilities:
    """What the current platform offers enforcement-wise."""

    platform: str
    enforcement_supported: bool
    reason: str
    euid: int | None = None
    privileged_hint: bool | None = None


def detect_capabilities() -> PlatformCapabilities:
    """Inspect the platform without changing anything."""
    if sys.platform != "linux":
        return PlatformCapabilities(
            platform=sys.platform,
            enforcement_supported=False,
            reason=f"enforcement requires Linux (running on {sys.platform})",
        )
    euid: int | None = None
    try:
        euid = os.geteuid()
    except AttributeError:
        euid = None
    return PlatformCapabilities(
        platform=sys.platform,
        enforcement_supported=True,
        reason="Linux resource control available via process APIs",
        euid=euid,
        privileged_hint=(euid == 0) if euid is not None else None,
    )
