#!/usr/bin/env python3
"""Claude Code PreCommit hook - validates changes against business rules.

This hook is triggered before code is committed in Claude Code.
It calls the AI Nexus pre-commit API to validate changes against
approved business rules and outputs warnings if violations are found.

Silent degradation: if the service is unavailable or times out, the hook
passes silently without blocking the commit.
"""

import asyncio
import json
import os
import sys

import httpx

# Configuration from environment
AI_NEXUS_URL = os.environ.get("AI_NEXUS_URL", "http://localhost:8000")
TIMEOUT = float(os.environ.get("AI_NEXUS_HOOK_TIMEOUT", "5.0"))


async def main() -> None:
    """Main hook entry point.

    Reads hook input from stdin, calls the pre-commit API, and outputs
    violation warnings if any are found.
    """
    try:
        # Read hook input from stdin
        hook_input_str = sys.stdin.read()
        if not hook_input_str:
            return

        hook_input = json.loads(hook_input_str)

        # Extract change information
        # The hook receives info about staged changes
        tool_input = hook_input.get("tool_input", {})
        change_description = json.dumps(tool_input, ensure_ascii=False)

        # Call the pre-commit API
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{AI_NEXUS_URL}/api/hooks/pre-commit",
                json={
                    "change_description": change_description,
                    "diff_summary": tool_input.get("diff"),
                },
            )
            if response.status_code == 200:
                data = response.json()
                violations = data.get("violations", [])

                if violations:
                    # Output violation warnings
                    warning_parts = ["<system-reminder>"]
                    warning_parts.append("⚠️ AI Nexus: Business Rule Violations Detected")
                    warning_parts.append("")

                    for violation in violations:
                        rule_name = violation.get("rule", "Unknown Rule")
                        description = violation.get("description", "")
                        severity = violation.get("severity", "warning")

                        if severity == "critical":
                            emoji = "🔴"
                        elif severity == "error":
                            emoji = "🟡"
                        else:
                            emoji = "⚠️"
                        warning_parts.append(f"{emoji} [{severity}] {rule_name}")
                        warning_parts.append(f"   {description}")
                        warning_parts.append("")

                    warning_parts.append("Please review these violations before committing.")
                    warning_parts.append("</system-reminder>")

                    print("\n".join(warning_parts), file=sys.stderr)

                    # Record violation events if violation_events endpoint exists
                    for violation in violations:
                        try:
                            await client.post(
                                f"{AI_NEXUS_URL}/api/violations/events",
                                json={
                                    "rule_id": violation.get("rule_id"),
                                    "change_description": change_description,
                                    "resolution": "pending",
                                },
                                timeout=TIMEOUT,
                            )
                        except Exception:
                            # Don't fail if event recording fails
                            pass

    except (httpx.TimeoutException, httpx.ConnectError):
        # Timeout or connection error - silent degradation
        pass
    except Exception:
        # Any other error - silent degradation, never block the commit
        pass


if __name__ == "__main__":
    asyncio.run(main())
