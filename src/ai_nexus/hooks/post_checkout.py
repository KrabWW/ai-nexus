#!/usr/bin/env python3
"""Claude Code post-checkout hook — clears cached context after branch switch.

This hook is triggered after git checkout in Claude Code.
It clears any cached business context to ensure fresh context
for the new branch.

Silent degradation: if the service is unavailable or times out, the hook
passes silently without affecting the checkout.
"""

import asyncio
import os
import subprocess

import httpx

# Configuration from environment
AI_NEXUS_URL = os.environ.get("AI_NEXUS_URL", "http://localhost:8000")
TIMEOUT = float(os.environ.get("AI_NEXUS_HOOK_TIMEOUT", "2.0"))


async def main() -> None:
    """Main hook entry point.

    Clears any cached business context after branch checkout.
    """
    try:
        # Get branch information from git
        try:
            current_branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            current_branch = "unknown"

        # Call the cache clear API
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{AI_NEXUS_URL}/api/hooks/post-checkout",
                json={"branch": current_branch},
            )

            if response.status_code == 200:
                data = response.json()
                cleared = data.get("cleared", False)
                if cleared:
                    print(f"[AI Nexus] Context cache cleared for branch: {current_branch}")

    except (httpx.TimeoutException, httpx.ConnectError):
        # Timeout or connection error - silent degradation
        pass
    except Exception:
        # Any other error - silent degradation, never affect the checkout
        pass


if __name__ == "__main__":
    asyncio.run(main())
