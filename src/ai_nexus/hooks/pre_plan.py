#!/usr/bin/env python3
"""Claude Code PreToolUse hook - injects business context before AI writes code.

This hook is triggered before Write/Edit tool use in Claude Code.
It calls the AI Nexus pre-plan API to retrieve relevant business context
and injects it as a system reminder for the AI.

Silent degradation: if the service is unavailable or times out, the hook
passes silently without blocking the AI.
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

    Reads hook input from stdin, calls the pre-plan API, and outputs
    business context as a system reminder.
    """
    try:
        # Read hook input from stdin (Claude Code provides tool input as JSON)
        hook_input_str = sys.stdin.read()
        if not hook_input_str:
            return

        hook_input = json.loads(hook_input_str)
        tool_input = hook_input.get("tool_input", {})

        # Extract task context from the tool input
        # For Write/Edit tools, the content or file_path provides context
        task_description = json.dumps(tool_input, ensure_ascii=False)

        # Call the pre-plan API
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{AI_NEXUS_URL}/api/hooks/pre-plan",
                json={"task_description": task_description},
            )
            if response.status_code == 200:
                data = response.json()
                context = data.get("context", "")

                # Build system reminder with business context
                if context:
                    entities = context.get("entities", [])
                    rules = context.get("rules", [])

                    if entities or rules:
                        reminder_parts = ["<system-reminder>"]
                        reminder_parts.append("AI Nexus Business Context:")

                        if entities:
                            reminder_parts.append("\nRelevant Entities:")
                            for entity in entities[:5]:
                                name = entity.get("name", "")
                                desc = entity.get("description", "")
                                reminder_parts.append(f"  - {name}: {desc}")

                        if rules:
                            reminder_parts.append("\nRelevant Business Rules:")
                            for rule in rules[:5]:
                                name = rule.get("name", "")
                                desc = rule.get("description", "")
                                severity = rule.get("severity", "info")
                                reminder_parts.append(f"  - [{severity}] {name}: {desc}")

                        reminder_parts.append("</system-reminder>")
                        print("\n".join(reminder_parts))

    except (httpx.TimeoutException, httpx.ConnectError):
        # Timeout or connection error - silent degradation
        pass
    except Exception:
        # Any other error - silent degradation, never block the AI
        pass


if __name__ == "__main__":
    asyncio.run(main())
