#!/usr/bin/env python3
"""Install CLI for Claude Code hooks.

This module provides a command-line interface to generate Claude Code
hooks configuration in .claude/settings.json.
"""

import argparse
import json
from pathlib import Path


def find_project_root() -> Path:
    """Find the project root directory by looking for .claude directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".claude").exists():
            return current
        current = current.parent
    return Path.cwd()


def generate_hooks_config(
    hook_scripts_dir: str,
    ai_nexus_url: str = "http://localhost:8000",
    include_git_hooks: bool = False,
) -> dict:
    """Generate the hooks configuration for Claude Code settings.json.

    Args:
        hook_scripts_dir: Path to the directory containing hook scripts
        ai_nexus_url: URL of the AI Nexus service
        include_git_hooks: Whether to include post-commit/post-checkout git hooks

    Returns:
        Dictionary with hooks configuration
    """
    pre_plan_path = f"python {hook_scripts_dir}/pre_plan.py"
    pre_commit_path = f"python {hook_scripts_dir}/pre_commit.py"

    config = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": pre_plan_path,
                        }
                    ],
                }
            ],
            "PreCommit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": pre_commit_path,
                        }
                    ]
                }
            ],
        },
        "env": {
            "AI_NEXUS_URL": ai_nexus_url,
            "AI_NEXUS_HOOK_TIMEOUT": "5.0",
        },
    }

    # Add git hooks if requested
    if include_git_hooks:
        post_commit_path = f"python {hook_scripts_dir}/post_commit.py"
        post_checkout_path = f"python {hook_scripts_dir}/post_checkout.py"

        config["hooks"]["PostCommit"] = [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": post_commit_path,
                    }
                ]
            }
        ]
        config["hooks"]["PostCheckout"] = [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": post_checkout_path,
                    }
                ]
            }
        ]

    return config


def install_hooks(
    hook_scripts_dir: str | None = None,
    ai_nexus_url: str = "http://localhost:8000",
    settings_path: str | None = None,
    include_git_hooks: bool = False,
) -> None:
    """Install Claude Code hooks configuration.

    Args:
        hook_scripts_dir: Path to hook scripts (relative to project root)
        ai_nexus_url: URL of the AI Nexus service
        settings_path: Custom path to settings.json (defaults to .claude/settings.json)
        include_git_hooks: Whether to include post-commit/post-checkout git hooks
    """
    project_root = find_project_root()
    settings_file = (
        Path(settings_path) if settings_path else project_root / ".claude" / "settings.json"
    )

    # Default hooks directory relative to project root
    if hook_scripts_dir is None:
        hook_scripts_dir = "src/ai_nexus/hooks"

    # Create .claude directory if it doesn't exist
    settings_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing settings if present
    existing_settings: dict = {}
    if settings_file.exists():
        with open(settings_file, encoding="utf-8") as f:
            existing_settings = json.load(f)

    # Generate new hooks configuration
    new_hooks_config = generate_hooks_config(hook_scripts_dir, ai_nexus_url, include_git_hooks)

    # Merge with existing settings, preserving non-hook settings
    merged_settings = {**existing_settings}
    merged_settings["hooks"] = new_hooks_config["hooks"]

    # Merge env settings, preserving existing env vars
    if "env" not in merged_settings:
        merged_settings["env"] = {}
    merged_settings["env"].update(new_hooks_config["env"])

    # Write merged settings
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(merged_settings, f, indent=2)

    print(f"✓ Claude Code hooks installed to: {settings_file}")
    print(f"  - PreToolUse hook: {hook_scripts_dir}/pre_plan.py")
    print(f"  - PreCommit hook: {hook_scripts_dir}/pre_commit.py")
    if include_git_hooks:
        print(f"  - PostCommit hook: {hook_scripts_dir}/post_commit.py")
        print(f"  - PostCheckout hook: {hook_scripts_dir}/post_checkout.py")
    print(f"  - AI Nexus URL: {ai_nexus_url}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Install Claude Code hooks for AI Nexus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m ai_nexus.hooks.install
  python -m ai_nexus.hooks.install --url http://localhost:8000
  python -m ai_nexus.hooks.install --url http://localhost:8000 --hooks-dir src/ai_nexus/hooks
  python -m ai_nexus.hooks.install --git-hooks
        """,
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="AI Nexus service URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--hooks-dir",
        help="Path to hook scripts directory (default: src/ai_nexus/hooks)",
    )
    parser.add_argument(
        "--settings",
        help="Custom path to Claude Code settings.json",
    )
    parser.add_argument(
        "--git-hooks",
        action="store_true",
        help="Include git hooks (post-commit, post-checkout)",
    )

    args = parser.parse_args()

    install_hooks(
        hook_scripts_dir=args.hooks_dir,
        ai_nexus_url=args.url,
        settings_path=args.settings,
        include_git_hooks=args.git_hooks,
    )


if __name__ == "__main__":
    main()
