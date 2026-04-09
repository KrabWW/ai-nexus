#!/usr/bin/env python3
"""Claude Code post-commit hook — extracts knowledge from committed changes.

This hook is triggered after code is committed in Claude Code.
It extracts business entities and rules from the commit message and diff,
then submits them as knowledge candidates for review.

Silent degradation: if the service is unavailable or times out, the hook
passes silently without affecting the commit.
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

    Reads hook input from stdin, extracts knowledge from commit,
    and submits candidates to the audit log.
    """
    try:
        # Read hook input from stdin
        hook_input_str = sys.stdin.read()
        if not hook_input_str:
            return

        hook_input = json.loads(hook_input_str)
        tool_input = hook_input.get("tool_input", {})

        # Get commit information
        # In a real git hook, we'd get this from git environment
        # For Claude Code, we extract from the input
        commit_message = tool_input.get("commit_message", "")
        diff = tool_input.get("diff", "")

        if not commit_message and not diff:
            return

        # Call the extraction API
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Submit for knowledge extraction
            payload = {
                "text": f"Commit: {commit_message}\n\nDiff:\n{diff[:2000]}",
                "source": "git-post-commit-hook",
                "confidence": 0.6,  # Default confidence for git hook extraction
            }

            response = await client.post(
                f"{AI_NEXUS_URL}/api/hooks/post-commit",
                json=payload,
            )

            if response.status_code == 200:
                data = response.json()
                extracted = data.get("extracted", {})
                entities_count = len(extracted.get("entities", []))
                rules_count = len(extracted.get("rules", []))

                if entities_count or rules_count:
                    # Output summary to user
                    print(
                        f"\n[AI Nexus] Extracted {entities_count} entities, "
                        f"{rules_count} rules from commit. "
                        f"Submitted for review."
                    )

    except (httpx.TimeoutException, httpx.ConnectError):
        # Timeout or connection error - silent degradation
        pass
    except Exception:
        # Any other error - silent degradation, never affect the commit
        pass


if __name__ == "__main__":
    asyncio.run(main())
