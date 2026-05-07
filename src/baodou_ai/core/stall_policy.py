from typing import Any, Dict, List, Optional


class StallPolicy:
    """停滞与循环检测策略。"""

    def __init__(self, action_signature_tolerance_px: int = 15) -> None:
        self._action_signature_tolerance_px = max(int(action_signature_tolerance_px or 0), 0)

    def is_stalled(
        self,
        previous_hash: Optional[str],
        current_hash: str,
        previous_signature: Optional[Dict[str, Any]],
        current_signature: Dict[str, Any],
    ) -> bool:
        if previous_hash is None or previous_signature is None:
            return False
        if previous_hash != current_hash:
            return False
        return self.is_same_tool_signature(previous_signature, current_signature)

    def is_same_tool_signature(
        self,
        previous_signature: Dict[str, Any],
        current_signature: Dict[str, Any],
    ) -> bool:
        if previous_signature["tool_name"] != current_signature["tool_name"]:
            return False
        if previous_signature["args"] != current_signature["args"]:
            return False

        tolerance = self._action_signature_tolerance_px
        previous_points = previous_signature["points"]
        current_points = current_signature["points"]
        if len(previous_points) != len(current_points):
            return False

        return all(
            abs(prev_x - curr_x) <= tolerance and abs(prev_y - curr_y) <= tolerance
            for (prev_x, prev_y), (curr_x, curr_y) in zip(previous_points, current_points)
        )

    def is_loop_report_required(
        self,
        current_screen_hash: str,
        recent_effective_history: List[Dict[str, Any]],
    ) -> bool:
        return (
            self.has_repeated_same_action_loop(current_screen_hash, recent_effective_history)
            or self.has_back_and_forth_loop(current_screen_hash, recent_effective_history)
        )

    def has_repeated_same_action_loop(
        self,
        current_screen_hash: str,
        recent_effective_history: List[Dict[str, Any]],
    ) -> bool:
        if len(recent_effective_history) < 2:
            return False

        repeated_count = 0
        last_signature = recent_effective_history[-1]["signature"]
        if not last_signature.get("points"):
            return False

        for entry in reversed(recent_effective_history):
            if entry["screen_hash"] != current_screen_hash:
                break
            if not self.is_same_tool_signature(entry["signature"], last_signature):
                break
            repeated_count += 1
        return repeated_count >= 2

    def has_back_and_forth_loop(
        self,
        current_screen_hash: str,
        recent_effective_history: List[Dict[str, Any]],
    ) -> bool:
        if len(recent_effective_history) < 4:
            return False

        last_four = recent_effective_history[-4:]
        hashes = [entry["screen_hash"] for entry in last_four]
        if any(hash_value != current_screen_hash for hash_value in hashes):
            return False

        first = last_four[0]["signature"]
        second = last_four[1]["signature"]
        third = last_four[2]["signature"]
        fourth = last_four[3]["signature"]
        if not first.get("points") or not second.get("points"):
            return False

        return (
            self.is_same_tool_signature(first, third)
            and self.is_same_tool_signature(second, fourth)
            and not self.is_same_tool_signature(first, second)
        )

