"""
页面稳定检测模块

为纯视觉自动化提供动作后的低成本稳定检测能力，
避免固定等待导致的空转或过早截图。
"""

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class SettleResult:
    """页面稳定检测结果。"""

    stable: bool
    probe_count: int
    elapsed_ms: float
    last_change_ratio: float


class ScreenSettler:
    """基于低清探测图的页面稳定检测器。"""

    def __init__(self, screenshot_capture, config) -> None:
        self._screenshot = screenshot_capture
        self._config = config

    def wait_until_stable(
        self,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> SettleResult:
        """等待所有屏幕进入稳定状态，超时后强制放行。"""
        execution_config = self._config.execution_config
        min_wait_ms = execution_config.get("settle_min_wait_ms", 250)
        probe_interval_ms = execution_config.get("settle_probe_interval_ms", 100)
        required_stable = execution_config.get("settle_required_stable_probes", 3)
        max_wait_ms = execution_config.get("settle_max_wait_ms", 4000)
        probe_width = execution_config.get("settle_probe_width", 160)
        probe_height = execution_config.get("settle_probe_height", 90)
        change_threshold = execution_config.get("settle_change_threshold", 0.01)

        start_time = time.perf_counter()
        stable_probe_count = 0
        previous_probes: Optional[List[Dict[str, Any]]] = None
        last_change_ratio = 1.0
        probe_count = 0

        while True:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            if should_stop is not None and should_stop():
                return SettleResult(
                    stable=False,
                    probe_count=probe_count,
                    elapsed_ms=elapsed_ms,
                    last_change_ratio=last_change_ratio,
                )
            if elapsed_ms >= max_wait_ms:
                return SettleResult(
                    stable=False,
                    probe_count=probe_count,
                    elapsed_ms=elapsed_ms,
                    last_change_ratio=last_change_ratio,
                )

            success, current_probes = self._screenshot.capture_screen_probes(
                screen_info=screen_info,
                probe_width=probe_width,
                probe_height=probe_height,
            )
            probe_count += 1

            if not success or not current_probes:
                self._sleep_probe_interval(probe_interval_ms, should_stop)
                continue

            if previous_probes is None:
                previous_probes = current_probes
                last_change_ratio = 1.0
                stable_probe_count = 0
                self._sleep_probe_interval(probe_interval_ms, should_stop)
                continue

            last_change_ratio = self._calculate_change_ratio(previous_probes, current_probes)
            previous_probes = current_probes

            if elapsed_ms >= min_wait_ms and last_change_ratio <= change_threshold:
                stable_probe_count += 1
                if stable_probe_count >= required_stable:
                    return SettleResult(
                        stable=True,
                        probe_count=probe_count,
                        elapsed_ms=elapsed_ms,
                        last_change_ratio=last_change_ratio,
                    )
            else:
                stable_probe_count = 0

            self._sleep_probe_interval(probe_interval_ms, should_stop)

    @staticmethod
    def _sleep_probe_interval(
        probe_interval_ms: float,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> None:
        deadline = time.perf_counter() + max(float(probe_interval_ms or 0), 0.0) / 1000.0
        while True:
            if should_stop is not None and should_stop():
                return
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.05))

    def _calculate_change_ratio(
        self,
        previous_probes: List[Dict[str, Any]],
        current_probes: List[Dict[str, Any]],
    ) -> float:
        """计算所有屏幕探测图之间的平均变化率。"""
        previous_map = {probe["index"]: probe["gray"] for probe in previous_probes}
        current_map = {probe["index"]: probe["gray"] for probe in current_probes}
        change_ratios: List[float] = []

        for screen_index, current_gray in current_map.items():
            previous_gray = previous_map.get(screen_index)
            if previous_gray is None or current_gray.shape != previous_gray.shape:
                change_ratios.append(1.0)
                continue

            diff = self._screenshot.calculate_image_difference(previous_gray, current_gray)
            change_ratios.append(diff)

        if not change_ratios:
            return 1.0

        return max(change_ratios)
