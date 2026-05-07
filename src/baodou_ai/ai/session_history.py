import json
import os
from datetime import datetime
from typing import Dict, List


class SessionHistory:
    DEFAULT_MAX_TASKS = 5

    def __init__(self, file_path: str = "~/.baodou/session_history.json", max_tasks: int = DEFAULT_MAX_TASKS):
        self.file_path = os.path.expanduser(file_path)
        self.max_tasks = max(1, min(10, max_tasks))
        self._tasks: List[Dict] = self._load()
        self._trim_tasks()

    def _load(self) -> List[Dict]:
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
        except Exception:
            pass
        return []

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._tasks, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_task(
        self,
        instruction: str,
        status: str,
        report: str,
        memory: str,
        steps: int,
        include_in_context: bool = True,
        context_report: str = "",
    ) -> None:
        task = {
            "instruction": instruction,
            "status": status,
            "report": report,
            "context_report": context_report,
            "memory": memory,
            "steps": steps,
            "include_in_context": bool(include_in_context),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._tasks.append(task)
        self._trim_tasks()
        self._save()

    def _trim_tasks(self) -> None:
        if len(self._tasks) > self.max_tasks:
            self._tasks = self._tasks[-self.max_tasks:]

    def get_recent_tasks(self, count: int = 5) -> List[Dict]:
        return self._tasks[-count:]

    def set_max_tasks(self, max_tasks: int) -> None:
        self.max_tasks = max(1, min(10, max_tasks))
        self._trim_tasks()
        self._save()

    @staticmethod
    def build_interrupted_report(task_text: str, iterations: List[Dict]) -> str:
        last_iterations = iterations[-5:]
        extracted = []
        for it in last_iterations:
            tool_name = it.get("tool_name", "")
            action = it.get("action", "")
            if tool_name:
                extracted.append(f"{tool_name}({action})" if action else tool_name)
            elif action:
                extracted.append(action)
        kept = extracted[-3:]
        prefix = f'Task "{task_text}" was interrupted after {len(iterations)} steps.'
        if kept:
            return f"{prefix} Last actions: {' → '.join(kept)}"
        return prefix

    @staticmethod
    def build_failed_report(task_text: str, iterations: List[Dict], error: str) -> str:
        last_iterations = iterations[-5:]
        extracted = []
        for it in last_iterations:
            tool_name = it.get("tool_name", "")
            action = it.get("action", "")
            if tool_name:
                extracted.append(f"{tool_name}({action})" if action else tool_name)
            elif action:
                extracted.append(action)
        kept = extracted[-3:]
        prefix = f'Task "{task_text}" failed after {len(iterations)} steps.'
        if kept:
            return f"{prefix} Last actions: {' → '.join(kept)}. Error: {error}"
        return f"{prefix} Error: {error}"

    def _estimate_tokens(self, text: str) -> int:
        token_count = 0
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff":
                token_count += 2
            else:
                token_count += 1
        return token_count

    def build_context_prompt(self, token_budget: int = 1500) -> str:
        if not self._tasks:
            return ""

        visible_tasks = [task for task in self._tasks if task.get("include_in_context", True) is not False]
        if not visible_tasks:
            return ""
        lines = []
        for i, task in enumerate(visible_tasks, 1):
            instruction = task.get("instruction", "")
            status = task.get("status", "")
            report = task.get("report", "")
            context_report = task.get("context_report") or report
            memory = task.get("memory", "")
            steps = task.get("steps", 0)

            if status == "completed":
                line = f'{i}. User: "{instruction}" → Completed. Result: {context_report}'
            elif status == "interrupted":
                line = f'{i}. User: "{instruction}" → Interrupted ({steps} steps). Last actions: {context_report}'
                if memory:
                    memory_oneline = memory.replace("\n", " / ")
                    line += f"\n   Agent memory: {memory_oneline}"
            elif status == "failed":
                line = f'{i}. User: "{instruction}" → Failed ({steps} steps). {context_report}'
                if memory:
                    memory_oneline = memory.replace("\n", " / ")
                    line += f"\n   Agent memory: {memory_oneline}"
            else:
                continue
            lines.append(line)

        prompt = "[Task History]\n" + "\n".join(lines)

        if self._estimate_tokens(prompt) <= token_budget:
            return prompt

        task_lines = lines
        memories = []
        for idx, task in enumerate(visible_tasks):
            if task.get("status") in ("interrupted", "failed") and task.get("memory"):
                memories.append(idx)

        for idx in memories:
            if self._estimate_tokens(prompt) <= token_budget:
                break
            old_line = task_lines[idx]
            memory_marker = "\n   Agent memory: "
            marker_pos = old_line.find(memory_marker)
            if marker_pos != -1:
                task_lines[idx] = old_line[:marker_pos]
                prompt = "[Task History]\n" + "\n".join(task_lines)

        if self._estimate_tokens(prompt) <= token_budget:
            return prompt

        while len(task_lines) > 1 and self._estimate_tokens(prompt) > token_budget:
            task_lines = task_lines[1:]
            prompt = "[Task History]\n" + "\n".join(task_lines)

        if self._estimate_tokens(prompt) > token_budget:
            return ""

        return prompt

    def clear(self) -> None:
        self._tasks = []
        self._save()
