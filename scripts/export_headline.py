#!/usr/bin/env python3
"""Regenerate `reports/headline.md` (and `reports/headline_env.md`) from Postgres.

The README's headline table is never hand-typed — it is pasted verbatim
from this script's output, so the README cannot drift from what the
database actually holds (FR-56). Run via `make headline`.
"""

from __future__ import annotations

import datetime
import logging
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.data import DashboardError, fetch_latest_headline  # noqa: E402
from dashboard.format import order_solvers, to_display_table, to_markdown_table  # noqa: E402

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"


def _docker_version() -> str:
    """Return `docker --version` output, or a placeholder if Docker isn't on PATH."""
    try:
        result = subprocess.run(
            ["docker", "--version"], capture_output=True, text=True, timeout=5, check=False
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "not available"


def build_env_report() -> str:
    """Render the environment/provenance report (NFR-24) as markdown."""
    lines = [
        "# Environment the headline numbers were produced on",
        "",
        f"- Generated: {datetime.datetime.now(datetime.UTC).isoformat()}",
        f"- OS: {platform.platform()}",
        f"- Python: {platform.python_version()}",
        f"- Docker: {_docker_version()}",
        "- Strong tier: openrouter/qwen/qwen-2.5-72b-instruct (config/litellm_config.yaml)",
        "- Small tier: groq/llama-3.1-8b-instant (config/litellm_config.yaml)",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    """Query the latest headline row per solver and write it to `reports/`."""
    logging.basicConfig(level=logging.INFO)
    try:
        frame = fetch_latest_headline()
    except DashboardError as exc:
        logger.error("Could not fetch headline metrics: %s", exc)
        return 1

    if frame.empty:
        logger.error("No rows in benchmark.headline_metrics — has `make benchmark` been run?")
        return 1

    display = to_display_table(order_solvers(frame))
    markdown = to_markdown_table(display)

    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "headline.md").write_text(markdown + "\n")
    (REPORTS_DIR / "headline_env.md").write_text(build_env_report())
    logger.info("Wrote reports/headline.md and reports/headline_env.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
