#!/usr/bin/env python3
"""Run GUI and platform acceptance suites with timeout protection."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from typing import Dict, List, Sequence, Tuple

DEFAULT_TIMEOUT_SECONDS = 240

SUITES: Dict[str, List[str]] = {
    "gui": [
        "tests/test_floating_window.py",
        "tests/test_log_window.py",
    ],
    "platform": [
        "tests/test_platform_macos.py",
        "tests/test_platform_windows.py",
        "tests/test_platform_common.py",
    ],
    "capability": [
        "tests/test_automation.py::test_tool_launch_app_uses_platform_adapter",
        "tests/test_automation.py::test_tool_launch_app_returns_suggestions_without_auto_open",
        "tests/test_automation.py::test_tool_launch_app_propagates_app_launcher_fallback",
        "tests/test_automation.py::test_tool_open_in_browser_uses_platform_adapter",
        "tests/test_automation.py::test_tool_open_in_finder_uses_platform_adapter",
        "tests/test_automation.py::test_tool_open_in_finder_with_path",
        "tests/test_automation.py::test_tool_open_app_launcher_uses_platform_adapter",
        "tests/test_automation.py::test_tool_read_current_page_rejects_non_browser_frontmost_app",
        "tests/test_automation.py::test_tool_read_current_document_rejects_unsupported_frontmost_app",
        "tests/test_runner.py::test_runner_launch_app_app_launcher_fallback_is_injected_into_next_feedback",
        "tests/test_runner.py::test_runner_hides_windows_before_capture_and_restores_afterwards",
        "tests/test_runner.py::test_runner_waits_before_next_capture_after_successful_tool_call",
        "tests/test_runner.py::test_runner_replan_does_not_wait_before_next_capture",
        "tests/test_runner.py::test_runner_restores_external_focus_before_capture_and_injects_frontmost_prompt",
        "tests/test_runner.py::test_runner_injects_focus_fallback_prompt_when_external_focus_unavailable",
        "tests/test_runner.py::test_runner_clears_stale_external_frontmost_app_after_restore_failure",
    ],
}

SUITE_ORDER = ["gui", "platform", "capability"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run GUI/platform acceptance test suites.")
    parser.add_argument(
        "--suite",
        choices=["gui", "platform", "capability", "all"],
        default="all",
        help="Suite to run. Default: all.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-suite timeout in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}.",
    )
    parser.add_argument(
        "--no-offscreen",
        action="store_true",
        help="Do not force QT_QPA_PLATFORM=offscreen.",
    )
    return parser.parse_args()


def build_pytest_env(no_offscreen: bool) -> Dict[str, str]:
    env = os.environ.copy()
    if not no_offscreen:
        env["QT_QPA_PLATFORM"] = "offscreen"
    return env


def run_suite(
    suite_name: str,
    targets: Sequence[str],
    timeout_seconds: int,
    no_offscreen: bool,
) -> Tuple[int, float, str]:
    env = build_pytest_env(no_offscreen=no_offscreen)
    command = [sys.executable, "-m", "pytest", "-q", *targets]
    started_at = time.time()

    print(f"\n=== [suite: {suite_name}] start ===")
    print(f"[suite:{suite_name}] timeout={timeout_seconds}s")
    if not no_offscreen:
        print(f"[suite:{suite_name}] QT_QPA_PLATFORM=offscreen")
    print(f"[suite:{suite_name}] command: {' '.join(command)}")
    sys.stdout.flush()

    try:
        completed = subprocess.run(
            command,
            env=env,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.time() - started_at
        message = (
            f"[suite:{suite_name}] TIMEOUT after {elapsed:.1f}s. "
            f"Likely stuck suite: {suite_name}."
        )
        print(message)
        return 124, elapsed, message

    elapsed = time.time() - started_at
    if completed.returncode == 0:
        message = f"[suite:{suite_name}] PASS in {elapsed:.1f}s"
    else:
        message = f"[suite:{suite_name}] FAIL (exit={completed.returncode}) in {elapsed:.1f}s"
    print(message)
    return completed.returncode, elapsed, message


def main() -> int:
    args = parse_args()

    if args.timeout_seconds <= 0:
        print("--timeout-seconds must be > 0")
        return 2

    suites = SUITE_ORDER if args.suite == "all" else [args.suite]
    summary: List[Tuple[str, int, float, str]] = []

    for suite_name in suites:
        code, elapsed, message = run_suite(
            suite_name=suite_name,
            targets=SUITES[suite_name],
            timeout_seconds=args.timeout_seconds,
            no_offscreen=args.no_offscreen,
        )
        summary.append((suite_name, code, elapsed, message))
        if code != 0:
            print(f"\nStop on first failed suite: {suite_name}")
            break

    print("\n=== acceptance summary ===")
    for suite_name, code, elapsed, _message in summary:
        status = "PASS" if code == 0 else ("TIMEOUT" if code == 124 else f"FAIL({code})")
        print(f"- {suite_name}: {status} ({elapsed:.1f}s)")

    for _suite_name, code, _elapsed, _message in summary:
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
