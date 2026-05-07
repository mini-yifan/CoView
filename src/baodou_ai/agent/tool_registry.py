"""
GUI 工具注册与参数归一化。
"""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Tuple

from baodou_ai.agent.schemas import (
    get_tool_json_schema as _get_tool_json_schema,
    normalize_tool_args_with_schema,
)


ToolArgs = Dict[str, Any]
Validator = Callable[[Dict[str, Any]], ToolArgs]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    args_prompt: str
    validator: Validator


def _normalize_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是整数") from exc


def _normalize_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是数字") from exc


def _normalize_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    raise ValueError(f"{field_name} 必须是布尔值")


def _normalize_text(value: Any, field_name: str, allow_empty: bool = False) -> str:
    if value is None:
        raise ValueError(f"{field_name} 不能为空")
    text = str(value)
    if not allow_empty and not text.strip():
        raise ValueError(f"{field_name} 不能为空")
    return text


def _normalize_position(value: Any, field_name: str) -> List[float]:
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{field_name} 必须是 [x, y] 格式")

    position: List[float] = []
    for index, item in enumerate(value):
        try:
            number = float(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name}[{index}] 必须是数字") from exc
        if number < 0 or number > 1000:
            raise ValueError(f"{field_name}[{index}] 必须在 0-1000 之间")
        position.append(number)
    return position


def _normalize_keys(value: Any) -> List[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("keys 必须是非空数组")

    normalized: List[str] = []
    for item in value:
        raw_text = _normalize_text(item, "keys", allow_empty=True)
        lowered = raw_text.strip().lower()
        if raw_text == " " or lowered in {"space", "spacebar"}:
            normalized.append("space")
            continue
        if not lowered:
            raise ValueError("keys 不能为空")
        normalized.append(lowered)
    return normalized


def _normalize_modifier_key(value: Any) -> str:
    lowered = _normalize_text(value, "keys").strip().lower()
    alias_map = {
        "cmd": "command",
        "ctl": "ctrl",
        "meta": "win",
        "windows": "win",
    }
    lowered = alias_map.get(lowered, lowered)
    if lowered not in {"command", "shift", "option", "control", "ctrl", "alt", "win"}:
        raise ValueError("只允许修饰键进入长按状态")
    return lowered


def _normalize_modifier_keys(value: Any) -> List[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("keys 必须是非空数组")

    normalized: List[str] = []
    seen = set()
    for item in value:
        key = _normalize_modifier_key(item)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def _normalize_click_args(args: Dict[str, Any]) -> ToolArgs:
    return {
        "screen_index": _normalize_int(args.get("screen_index", 0), "screen_index"),
        "position": _normalize_position(args.get("position"), "position"),
    }


def _normalize_scroll_args(args: Dict[str, Any]) -> ToolArgs:
    if "multiplier" in args:
        raise ValueError("滚动工具已改用 scroll_level 参数，不再接受 multiplier")
    normalized = _normalize_click_args(args)
    scroll_level = _normalize_int(args.get("scroll_level", 5), "scroll_level")
    if scroll_level < 1 or scroll_level > 10:
        raise ValueError("scroll_level 必须在 1-10 之间")
    normalized["scroll_level"] = scroll_level
    return normalized


def _normalize_long_press_args(args: Dict[str, Any]) -> ToolArgs:
    normalized = _normalize_click_args(args)
    duration_seconds = _normalize_float(args.get("duration_seconds", 3), "duration_seconds")
    if duration_seconds < 1 or duration_seconds > 10:
        raise ValueError("duration_seconds 必须在 1-10 秒之间")
    normalized["duration_seconds"] = duration_seconds
    return normalized


def _normalize_drag_args(args: Dict[str, Any]) -> ToolArgs:
    return {
        "start_screen_index": _normalize_int(args.get("start_screen_index", 0), "start_screen_index"),
        "start_position": _normalize_position(args.get("start_position"), "start_position"),
        "end_screen_index": _normalize_int(args.get("end_screen_index", 0), "end_screen_index"),
        "end_position": _normalize_position(args.get("end_position"), "end_position"),
    }


def _normalize_hotkey_args(args: Dict[str, Any]) -> ToolArgs:
    return {
        "keys": _normalize_keys(args.get("keys")),
    }


def _normalize_page_loading_args(args: Dict[str, Any]) -> ToolArgs:
    if args is None:
        return {"mode": "short_wait"}
    if not isinstance(args, dict):
        raise ValueError("page_loading 的参数必须是对象")

    extra_keys = sorted(set(args.keys()) - {"mode", "wait_seconds"})
    if extra_keys:
        raise ValueError(f"page_loading 不支持的字段: {', '.join(extra_keys)}")

    mode = str(args.get("mode") or "short_wait").strip().lower()
    if mode not in {"short_wait", "long_wait"}:
        raise ValueError("page_loading.mode 只能是 short_wait 或 long_wait")
    if mode == "short_wait":
        return {"mode": "short_wait"}

    wait_seconds_raw = args.get("wait_seconds", 3)
    try:
        wait_seconds = int(wait_seconds_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("page_loading.wait_seconds 必须是整数") from exc
    if wait_seconds < 1 or wait_seconds > 10:
        raise ValueError("page_loading.wait_seconds 必须在 1-10 之间")
    return {
        "mode": "long_wait",
        "wait_seconds": wait_seconds,
    }


def _normalize_input_text_args(args: Dict[str, Any]) -> ToolArgs:
    text = _normalize_text(args.get("text"), "text")
    has_screen_index = "screen_index" in args and args.get("screen_index") is not None
    has_position = "position" in args and args.get("position") is not None
    replace = _normalize_bool(args.get("replace", False), "replace")
    submit = _normalize_bool(args.get("submit", False), "submit")

    if has_screen_index != has_position:
        raise ValueError("input_text 传入坐标时必须同时提供 screen_index 和 position")

    normalized_args: ToolArgs = {
        "text": text,
        "replace": replace,
        "submit": submit,
    }
    if has_screen_index and has_position:
        normalized_args["screen_index"] = _normalize_int(args.get("screen_index", 0), "screen_index")
        normalized_args["position"] = _normalize_position(args.get("position"), "position")
    if replace and not (has_screen_index and has_position):
        raise ValueError("input_text(replace=true) 必须同时提供 screen_index 和 position")
    return normalized_args


def _normalize_remember_args(args: Dict[str, Any]) -> ToolArgs:
    return {
        "content": _normalize_text(args.get("content"), "content"),
    }


def _normalize_launch_app_args(args: Dict[str, Any]) -> ToolArgs:
    return {
        "app_name": _normalize_text(args.get("app_name"), "app_name"),
    }


def _normalize_open_app_launcher_args(args: Dict[str, Any]) -> ToolArgs:
    if args is None:
        return {}
    if not isinstance(args, dict):
        raise ValueError("open_app_launcher 的参数必须是对象")
    return {}


def _normalize_open_in_browser_args(args: Dict[str, Any]) -> ToolArgs:
    has_url = "url" in args and args.get("url") is not None
    has_query = "query" in args and args.get("query") is not None

    if has_url == has_query:
        raise ValueError("open_in_browser 必须且只能提供 url 或 query 其中一个")

    if has_url:
        return {
            "url": _normalize_text(args.get("url"), "url"),
        }

    return {
        "query": _normalize_text(args.get("query"), "query"),
    }


PATH_BLACKLIST = (
    "/System",
    "/private",
    "/etc",
    "/var",
    "/usr",
    "/sbin",
    "/bin",
    "/dev",
    "/proc",
    "/sys",
)


def _is_path_blacklisted(resolved_path: str) -> bool:
    for prefix in PATH_BLACKLIST:
        if resolved_path == prefix or resolved_path.startswith(prefix + "/"):
            return True
    return False


def _normalize_open_in_finder_args(args: Dict[str, Any]) -> ToolArgs:
    if args is None:
        return {}
    if not isinstance(args, dict):
        raise ValueError("open_in_finder 的参数必须是对象")

    raw_path = args.get("path")
    if raw_path is None:
        return {}

    path_text = _normalize_text(raw_path, "path").strip()
    if not path_text:
        raise ValueError("path 不能为空字符串")

    try:
        resolved = str(Path(path_text).expanduser().resolve())
    except Exception as exc:
        raise ValueError(f"path 路径无效: {exc}") from exc

    if _is_path_blacklisted(resolved):
        raise ValueError(f"不允许打开系统敏感路径: {resolved}")

    return {"path": resolved}


def _normalize_read_current_page_args(args: Dict[str, Any]) -> ToolArgs:
    if args is None:
        return {
            "mode": "extract",
        }
    if not isinstance(args, dict):
        raise ValueError("read_current_page 的参数必须是对象")

    mode = _normalize_text(args.get("mode", "extract"), "mode").strip().lower()
    if mode not in {"extract", "chunk", "next", "search"}:
        raise ValueError('read_current_page.mode 只能是 "extract"、"chunk"、"next" 或 "search"')

    has_chunk_index = "chunk_index" in args and args.get("chunk_index") is not None
    has_query = "query" in args and args.get("query") is not None
    has_top_k = "top_k" in args and args.get("top_k") is not None

    normalized_args: ToolArgs = {
        "mode": mode,
    }

    if mode == "extract":
        if has_chunk_index:
            raise ValueError("read_current_page(mode=extract) 不接受 chunk_index")
        if has_query or has_top_k:
            raise ValueError("read_current_page(mode=extract) 不接受 query 或 top_k")
        return normalized_args

    if mode == "chunk":
        if has_query or has_top_k:
            raise ValueError("read_current_page(mode=chunk) 不接受 query 或 top_k")
        if not has_chunk_index:
            raise ValueError("read_current_page(mode=chunk) 必须提供 chunk_index")
        normalized_chunk_index = _normalize_int(args.get("chunk_index"), "chunk_index")
        if normalized_chunk_index < 0:
            raise ValueError("chunk_index 必须是非负整数")
        normalized_args["chunk_index"] = normalized_chunk_index
        return normalized_args

    if mode == "next":
        if has_query or has_top_k:
            raise ValueError("read_current_page(mode=next) 不接受 query 或 top_k")
        if has_chunk_index:
            raise ValueError("read_current_page(mode=next) 不接受 chunk_index")
        return normalized_args

    if has_chunk_index:
        raise ValueError("read_current_page(mode=search) 不接受 chunk_index")
    if not has_query:
        raise ValueError("read_current_page(mode=search) 必须提供 query")
    normalized_query = _normalize_text(args.get("query"), "query").strip()
    if not normalized_query:
        raise ValueError("read_current_page(mode=search) 必须提供非空 query")
    normalized_args["query"] = normalized_query
    normalized_top_k = _normalize_int(args.get("top_k", 3), "top_k")
    if normalized_top_k <= 0:
        raise ValueError("top_k 必须是正整数")
    normalized_args["top_k"] = normalized_top_k
    return normalized_args


def _normalize_read_current_document_args(args: Dict[str, Any]) -> ToolArgs:
    if args is None:
        return {
            "mode": "extract",
            "follow_view": False,
        }
    if not isinstance(args, dict):
        raise ValueError("read_current_document 的参数必须是对象")

    mode = _normalize_text(args.get("mode", "extract"), "mode").strip().lower()
    if mode not in {"extract", "chunk", "next", "search"}:
        raise ValueError('read_current_document.mode 只能是 "extract"、"chunk"、"next" 或 "search"')

    has_screen_index = "screen_index" in args and args.get("screen_index") is not None
    has_position = "position" in args and args.get("position") is not None
    has_chunk_index = "chunk_index" in args and args.get("chunk_index") is not None
    has_query = "query" in args and args.get("query") is not None
    has_top_k = "top_k" in args and args.get("top_k") is not None

    normalized_args: ToolArgs = {
        "mode": mode,
        "follow_view": _normalize_bool(args.get("follow_view", False), "follow_view"),
    }

    if mode == "extract":
        if has_screen_index != has_position:
            raise ValueError("read_current_document 传入坐标时必须同时提供 screen_index 和 position")
        if has_chunk_index:
            raise ValueError("read_current_document(mode=extract) 不接受 chunk_index")
        if has_query or has_top_k:
            raise ValueError("read_current_document(mode=extract) 不接受 query 或 top_k")
        if has_screen_index:
            normalized_args["screen_index"] = _normalize_int(args.get("screen_index", 0), "screen_index")
            normalized_args["position"] = _normalize_position(args.get("position"), "position")
        return normalized_args

    if has_screen_index or has_position:
        raise ValueError("read_current_document 的 chunk/next/search 模式不接受坐标")

    if mode == "chunk":
        if has_query or has_top_k:
            raise ValueError("read_current_document(mode=chunk) 不接受 query 或 top_k")
        if not has_chunk_index:
            raise ValueError("read_current_document(mode=chunk) 必须提供 chunk_index")
        normalized_chunk_index = _normalize_int(args.get("chunk_index"), "chunk_index")
        if normalized_chunk_index < 0:
            raise ValueError("chunk_index 必须是非负整数")
        normalized_args["chunk_index"] = normalized_chunk_index
        return normalized_args

    if mode == "next":
        if has_query or has_top_k:
            raise ValueError("read_current_document(mode=next) 不接受 query 或 top_k")
        if has_chunk_index:
            raise ValueError("read_current_document(mode=next) 不接受 chunk_index")
        return normalized_args

    if has_chunk_index:
        raise ValueError("read_current_document(mode=search) 不接受 chunk_index")
    if not has_query:
        raise ValueError("read_current_document(mode=search) 必须提供 query")
    normalized_query = _normalize_text(args.get("query"), "query").strip()
    if not normalized_query:
        raise ValueError("read_current_document(mode=search) 必须提供非空 query")
    normalized_args["query"] = normalized_query
    normalized_top_k = _normalize_int(args.get("top_k", 3), "top_k")
    if normalized_top_k <= 0:
        raise ValueError("top_k 必须是正整数")
    normalized_args["top_k"] = normalized_top_k
    return normalized_args


def _normalize_hold_modifier_keys_args(args: Dict[str, Any]) -> ToolArgs:
    return {
        "keys": _normalize_modifier_keys(args.get("keys")),
    }


def _normalize_release_modifier_keys_args(args: Dict[str, Any]) -> ToolArgs:
    if args is None:
        return {}
    if not isinstance(args, dict):
        raise ValueError("release_modifier_keys 的参数必须是对象")
    if "keys" not in args or args.get("keys") is None:
        return {}
    return {
        "keys": _normalize_modifier_keys(args.get("keys")),
    }


MANAGE_FILES_MAX_BATCH = 20
MANAGE_FILES_BATCH_LIMIT_TEXT = (
    f"`delete` and `create` can include at most {MANAGE_FILES_MAX_BATCH} items in one call; "
    "if more items are needed, split them across multiple tool calls."
)


def _normalize_manage_files_args(args: Dict[str, Any]) -> ToolArgs:
    if args is None:
        return {"mode": "list"}
    if not isinstance(args, dict):
        raise ValueError("manage_files 的参数必须是对象")

    mode = _normalize_text(args.get("mode"), "mode").strip().lower()
    if mode not in ("list", "delete", "create", "move", "rename", "search"):
        raise ValueError(f"manage_files 的 mode 必须是 list/delete/create/move/rename/search 之一，收到: {mode}")

    result: ToolArgs = {"mode": mode}

    if mode == "list":
        raw_path = args.get("path")
        if raw_path is not None:
            path_text = _normalize_text(raw_path, "path").strip()
            if path_text:
                resolved = str(Path(path_text).expanduser().resolve())
                if _is_path_blacklisted(resolved):
                    raise ValueError(f"不允许访问系统敏感路径: {resolved}")
                result["path"] = resolved
        return result

    if mode == "search":
        raw_path = args.get("path")
        if raw_path is not None:
            path_text = _normalize_text(raw_path, "path").strip()
            if path_text:
                resolved = str(Path(path_text).expanduser().resolve())
                if _is_path_blacklisted(resolved):
                    raise ValueError(f"不允许访问系统敏感路径: {resolved}")
                result["path"] = resolved
        raw_query = args.get("query")
        if not raw_query:
            raise ValueError("search 模式必须提供 query 搜索词")
        result["query"] = _normalize_text(raw_query, "query").strip()
        return result

    if mode == "delete":
        raw_paths = args.get("paths")
        if not raw_paths or not isinstance(raw_paths, list):
            raise ValueError("delete 模式必须提供 paths 数组")
        if len(raw_paths) > MANAGE_FILES_MAX_BATCH:
            raise ValueError(f"单次最多删除 {MANAGE_FILES_MAX_BATCH} 个条目")
        resolved_paths = []
        for p in raw_paths:
            path_text = _normalize_text(p, "paths 中的路径").strip()
            resolved = str(Path(path_text).expanduser().resolve())
            if _is_path_blacklisted(resolved):
                raise ValueError(f"不允许操作系统敏感路径: {resolved}")
            resolved_paths.append(resolved)
        result["paths"] = resolved_paths
        return result

    if mode == "create":
        raw_parent = args.get("parent")
        if raw_parent is not None:
            parent_text = _normalize_text(raw_parent, "parent").strip()
            if parent_text:
                resolved = str(Path(parent_text).expanduser().resolve())
                if _is_path_blacklisted(resolved):
                    raise ValueError(f"不允许访问系统敏感路径: {resolved}")
                result["parent"] = resolved

        raw_items = args.get("items")
        if not raw_items or not isinstance(raw_items, list):
            raise ValueError("create 模式必须提供 items 数组")
        if len(raw_items) > MANAGE_FILES_MAX_BATCH:
            raise ValueError(f"单次最多创建 {MANAGE_FILES_MAX_BATCH} 个条目")
        normalized_items = []
        for item in raw_items:
            if not isinstance(item, dict):
                raise ValueError("items 中的每个条目必须是对象")
            name = _normalize_text(item.get("name"), "name").strip()
            if not name:
                raise ValueError("items 中的 name 不能为空")
            if "/" in name or "\\" in name:
                raise ValueError(f"名称中不能包含路径分隔符: {name}")
            item_type = _normalize_text(item.get("type", "file"), "type").strip().lower()
            if item_type not in ("file", "folder"):
                raise ValueError(f"type 必须是 file 或 folder，收到: {item_type}")
            normalized_items.append({"name": name, "type": item_type})
        result["items"] = normalized_items
        return result

    if mode == "move":
        raw_source = args.get("source")
        if not raw_source:
            raise ValueError("move 模式必须提供 source 路径")
        source_text = _normalize_text(raw_source, "source").strip()
        resolved_source = str(Path(source_text).expanduser().resolve())
        if _is_path_blacklisted(resolved_source):
            raise ValueError(f"不允许操作系统敏感路径: {resolved_source}")
        result["source"] = resolved_source

        raw_dest = args.get("destination")
        if not raw_dest:
            raise ValueError("move 模式必须提供 destination 路径")
        dest_text = _normalize_text(raw_dest, "destination").strip()
        resolved_dest = str(Path(dest_text).expanduser().resolve())
        if _is_path_blacklisted(resolved_dest):
            raise ValueError(f"不允许访问系统敏感路径: {resolved_dest}")
        result["destination"] = resolved_dest
        return result

    if mode == "rename":
        raw_path = args.get("path")
        if not raw_path:
            raise ValueError("rename 模式必须提供 path 路径")
        path_text = _normalize_text(raw_path, "path").strip()
        resolved = str(Path(path_text).expanduser().resolve())
        if _is_path_blacklisted(resolved):
            raise ValueError(f"不允许操作系统敏感路径: {resolved}")
        result["path"] = resolved

        raw_new_name = args.get("new_name")
        if not raw_new_name:
            raise ValueError("rename 模式必须提供 new_name")
        new_name = _normalize_text(raw_new_name, "new_name").strip()
        if not new_name:
            raise ValueError("new_name 不能为空")
        if "/" in new_name or "\\" in new_name:
            raise ValueError(f"new_name 中不能包含路径分隔符: {new_name}")
        result["new_name"] = new_name
        return result

    return result


def _normalize_code_agent_args(args: Dict[str, Any]) -> ToolArgs:
    if args is None:
        raise ValueError("code_agent 的参数必须是对象")
    if not isinstance(args, dict):
        raise ValueError("code_agent 的参数必须是对象")

    normalized: ToolArgs = {
        "task": _normalize_text(args.get("task"), "task"),
    }

    raw_title = args.get("title")
    if raw_title is not None:
        normalized["title"] = _normalize_text(raw_title, "title")

    raw_goal = args.get("goal")
    if raw_goal is not None:
        normalized["goal"] = _normalize_text(raw_goal, "goal")

    raw_job_id = args.get("job_id")
    if raw_job_id is not None:
        job_id = _normalize_text(raw_job_id, "job_id").strip()
        if not job_id:
            raise ValueError("job_id 不能为空")
        normalized["job_id"] = job_id

    raw_workspace_path = args.get("workspace_path")
    if raw_workspace_path is not None:
        workspace_path = _normalize_text(raw_workspace_path, "workspace_path").strip()
        if not workspace_path:
            raise ValueError("workspace_path 不能为空")
        resolved = str(Path(workspace_path).expanduser().resolve())
        normalized["workspace_path"] = resolved

    raw_timeout = args.get("timeout_seconds")
    if raw_timeout is not None:
        timeout_seconds = _normalize_int(raw_timeout, "timeout_seconds")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须是正整数")
        normalized["timeout_seconds"] = timeout_seconds

    return normalized


def _normalize_stop_code_agent_args(args: Dict[str, Any]) -> ToolArgs:
    if args is None:
        raise ValueError("stop_code_agent 的参数必须是对象")
    if not isinstance(args, dict):
        raise ValueError("stop_code_agent 的参数必须是对象")

    return {
        "job_id": _normalize_text(args.get("job_id"), "job_id"),
    }


TOOL_DEFINITIONS: Dict[str, ToolDefinition] = {
    "click": ToolDefinition(
        name="click",
        description="Perform a single click at the specified screen coordinates. Do not use this as a focus step before input; if the next step is to input text, use input_text directly.",
        args_prompt='{"screen_index": 0, "position": [500, 500]}',
        validator=_normalize_click_args,
    ),
    "double_click": ToolDefinition(
        name="double_click",
        description="Perform a double click at the specified screen coordinates.",
        args_prompt='{"screen_index": 0, "position": [500, 500]}',
        validator=_normalize_click_args,
    ),
    "long_press": ToolDefinition(
        name="long_press",
        description="Press and hold the left mouse button at the specified screen coordinates. `duration_seconds` controls how long to hold, from 1 to 10 seconds; default is 3 seconds.",
        args_prompt='{"screen_index": 0, "position": [500, 500]} or {"screen_index": 0, "position": [500, 500], "duration_seconds": 3}',
        validator=_normalize_long_press_args,
    ),
    "right_click": ToolDefinition(
        name="right_click",
        description="Perform a right click at the specified screen coordinates.",
        args_prompt='{"screen_index": 0, "position": [500, 500]}',
        validator=_normalize_click_args,
    ),
    "drag": ToolDefinition(
        name="drag",
        description="Drag from the start point to the end point, supports cross-screen.",
        args_prompt='{"start_screen_index": 0, "start_position": [400, 300], "end_screen_index": 1, "end_position": [650, 420]}',
        validator=_normalize_drag_args,
    ),
    "scroll_up": ToolDefinition(
        name="scroll_up",
        description="Scroll up at the given coordinates. `scroll_level` is 1-10 (default 5); start with 5 and adjust only when needed.",
        args_prompt='{"screen_index": 0, "position": [500, 700]} or {"screen_index": 0, "position": [500, 700], "scroll_level": 6}',
        validator=_normalize_scroll_args,
    ),
    "scroll_down": ToolDefinition(
        name="scroll_down",
        description="Scroll down at the given coordinates. `scroll_level` is 1-10 (default 5); start with 5 and adjust only when needed.",
        args_prompt='{"screen_index": 0, "position": [500, 700]} or {"screen_index": 0, "position": [500, 700], "scroll_level": 4}',
        validator=_normalize_scroll_args,
    ),
    "hotkey": ToolDefinition(
        name="hotkey",
        description="Execute a keyboard shortcut combination. Do not use it to close or minimize windows unless the user has explicitly agreed.",
        args_prompt='{"keys": ["command", "a"]}; for the space key, use {"keys": ["command", "space"]}',
        validator=_normalize_hotkey_args,
    ),
    "page_loading": ToolDefinition(
        name="page_loading",
        description="Wait before the next observation. `{}` is short wait; use `long_wait` only for explicit long-running states (install/download/export/LLM generating).",
        args_prompt='{} or {"mode": "long_wait", "wait_seconds": 3}',
        validator=_normalize_page_loading_args,
    ),
    "launch_app": ToolDefinition(
        name="launch_app",
        description="Launch or activate an app by name. Prefer this for opening/switching apps unless the user explicitly asks for a UI path (Dock/Launchpad/system search).",
        args_prompt='{"app_name": "WeChat"}',
        validator=_normalize_launch_app_args,
    ),
    "open_app_launcher": ToolDefinition(
        name="open_app_launcher",
        description="Open Launchpad and return scanned app names. Use for browsing installed apps or when the task explicitly requires Launchpad.",
        args_prompt="{}",
        validator=_normalize_open_app_launcher_args,
    ),
    "open_in_browser": ToolDefinition(
        name="open_in_browser",
        description="Open a URL or search text in the current default browser. Provide exactly one of `url` or `query`.",
        args_prompt='{"url": "https://www.bilibili.com"} or {"query": "Luoxiang Criminal Law bilibili"}',
        validator=_normalize_open_in_browser_args,
    ),
    "open_in_finder": ToolDefinition(
        name="open_in_finder",
        description='Open Finder to a target path. Folder path: open folder; file path: open containing folder and select file; no path: open Desktop. Build paths from [User Home Directory], do not guess username.',
        args_prompt='{} or {"path": "/Users/xxx/Desktop/test2"} or {"path": "/Users/xxx/Documents/report.pdf"}',
        validator=_normalize_open_in_finder_args,
    ),
    "manage_files": ToolDefinition(
        name="manage_files",
        description=(
            "Manage files/folders (Finder only). Modes: `list`, `search`, `delete`, `create`, `move`, `rename`. "
            "For `list`/`search`/`create`, target directory can be omitted to use current Finder folder. "
            f"Build paths from [User Home Directory], do not guess username. {MANAGE_FILES_BATCH_LIMIT_TEXT}"
        ),
        args_prompt=(
            '{"mode": "list"} or {"mode": "search", "query": "report"} or {"mode": "list", "path": "/Users/xxx/Desktop"} '
            'or {"mode": "delete", "paths": ["/Users/xxx/Desktop/test.txt"]} or {"mode": "create", "parent": "/Users/xxx/Desktop", '
            '"items": [{"name": "New Folder", "type": "folder"}, {"name": "notes.txt", "type": "file"}]} '
            'or {"mode": "move", "source": "/Users/xxx/Desktop/test.txt", "destination": "/Users/xxx/Documents"} '
            f'or {{"mode": "rename", "path": "/Users/xxx/Desktop/test.txt", "new_name": "report.txt"}}. {MANAGE_FILES_BATCH_LIMIT_TEXT}'
        ),
        validator=_normalize_manage_files_args,
    ),
    "read_current_page": ToolDefinition(
        name="read_current_page",
        description='Read main text from the current browser page. Modes: `extract`, `chunk`, `next`, `search`. Browser only; results may be incomplete. Run `extract` before `search`.',
        args_prompt='{"mode": "extract"} then {"mode": "search", "query": "refund penalty"}; optional {"mode": "chunk", "chunk_index": 0} or {"mode": "next"}',
        validator=_normalize_read_current_page_args,
    ),
    "read_current_document": ToolDefinition(
        name="read_current_document",
        description='Read main text from the current document/editor. Modes: `extract`, `chunk`, `next`, `search`. Run `extract` before `search`. In programming IDE/editor, `extract` must include `screen_index` and `position`.',
        args_prompt='{"mode": "extract"} or {"mode": "extract", "screen_index": 0, "position": [500, 500]} then {"mode": "search", "query": "refund penalty"}; optional {"mode": "chunk", "chunk_index": 0} or {"mode": "next"}',
        validator=_normalize_read_current_document_args,
    ),
    "hold_modifier_keys": ToolDefinition(
        name="hold_modifier_keys",
        description="Press and hold one or more modifier keys for reuse in subsequent multi-step operations. Only use when you truly need to hold modifier keys across multiple steps.",
        args_prompt='{"keys": ["command"]}',
        validator=_normalize_hold_modifier_keys_args,
    ),
    "release_modifier_keys": ToolDefinition(
        name="release_modifier_keys",
        description="Release the currently held modifier keys. When keys is not provided, all are released; when keys is provided, only the specified modifier keys are released.",
        args_prompt='{} or {"keys": ["command"]}',
        validator=_normalize_release_modifier_keys_args,
    ),
    "input_text": ToolDefinition(
        name="input_text",
        description="Unified text input. Prefer one call to click+type+enter when possible. Type at current focus or target position; optional `replace` and `submit`. If `replace=true`, `screen_index` and `position` are required.",
        args_prompt='{"text": "Hello"} or {"text": "收到，我现在处理。", "submit": true} or {"screen_index": 0, "position": [500, 160], "text": "weather in shanghai", "replace": true, "submit": true}',
        validator=_normalize_input_text_args,
    ),
    "remember": ToolDefinition(
        name="remember",
        description="Write important information that the current task needs to remember into memory.",
        args_prompt='{"content": "Alice, Bob, Charlie"}',
        validator=_normalize_remember_args,
    ),
    "code_agent": ToolDefinition(
        name="code_agent",
        description=(
            "Start or continue a background code-agent task."
            "\nUse this only for reusable deliverables (files/reports/code/scripts/spreadsheets/documents)."
            "\nDo NOT use for foreground GUI browsing, quick lookups, troubleshooting, or simple click/input tasks."
            "\n`task` is required and must preserve user scope exactly; do not add unstated goals or features."
            "\nOptional: `title`, `goal`, `job_id`, `workspace_path`, `timeout_seconds`."
            "\nSet `job_id` only when continuing a remembered task card."
            "\nWhen continuing (`job_id` present), rewrite a complete fresh `task` that merges explicit old + new requirements;"
            " do not send only deltas."
        ),
        args_prompt='{"task": "Generate a simple calculator HTML page with inline CSS and JavaScript"} or {"task": "Analyze CSV files and output an Excel summary", "title": "Data analysis report"} or {"job_id": "code-job-...", "task": "Continue current calculator task and add only a dark theme toggle", "title": "Refine calculator page"}',
        validator=_normalize_code_agent_args,
    ),
    "stop_code_agent": ToolDefinition(
        name="stop_code_agent",
        description="Stop a currently running background code-agent task by job_id. Use this only when the user clearly wants to stop, cancel, or terminate one of the currently remembered background code-agent tasks.",
        args_prompt='{"job_id": "code-job-..."}',
        validator=_normalize_stop_code_agent_args,
    ),
}


def get_tool_definition(name: str) -> ToolDefinition:
    normalized_name = str(name or "").strip()
    definition = TOOL_DEFINITIONS.get(normalized_name)
    if definition is None:
        raise ValueError(f"未知工具: {normalized_name}")
    return definition


def normalize_tool_args(name: str, args: Dict[str, Any] | None) -> ToolArgs:
    normalized_name = str(name or "").strip()
    get_tool_definition(normalized_name)
    if args is not None and not isinstance(args, dict):
        raise ValueError("tool.args 必须是对象")
    return normalize_tool_args_with_schema(normalized_name, args)


def get_tool_json_schema(name: str) -> Dict[str, Any]:
    normalized_name = str(name or "").strip()
    get_tool_definition(normalized_name)
    return _get_tool_json_schema(normalized_name)


def render_tool_prompt() -> str:
    lines = ["## Available GUI Tools", ""]
    for tool_name in TOOL_DEFINITIONS:
        if tool_name in {"remember", "page_loading"}:
            continue
        definition = TOOL_DEFINITIONS[tool_name]
        lines.append(f"- `{definition.name}`：{definition.description}")
        lines.append(f"  参数示例：`{definition.args_prompt}`")
    return "\n".join(lines)


def tool_call_to_legacy_fields(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    normalized_args = normalize_tool_args(tool_name, tool_args)

    if tool_name in {"click", "double_click", "right_click", "scroll_up", "scroll_down"}:
        return {
            "action": tool_name,
            "coordinates": normalized_args["position"],
            "type_information": "",
            "screen_index": normalized_args["screen_index"],
            "end_screen_index": normalized_args["screen_index"],
        }

    if tool_name == "long_press":
        return {
            "action": "long_press",
            "coordinates": normalized_args["position"],
            "type_information": f"duration_seconds={normalized_args['duration_seconds']}",
            "screen_index": normalized_args["screen_index"],
            "end_screen_index": normalized_args["screen_index"],
        }

    if tool_name == "drag":
        return {
            "action": "drag",
            "coordinates": [
                normalized_args["start_position"],
                normalized_args["end_position"],
            ],
            "type_information": "",
            "screen_index": normalized_args["start_screen_index"],
            "end_screen_index": normalized_args["end_screen_index"],
        }

    if tool_name == "hotkey":
        return {
            "action": "hotkey",
            "coordinates": [0, 0],
            "type_information": " ".join(normalized_args["keys"]),
            "screen_index": 0,
            "end_screen_index": 0,
        }

    if tool_name == "page_loading":
        return {
            "action": "page_loading",
            "coordinates": [0, 0],
            "type_information": "",
            "screen_index": 0,
            "end_screen_index": 0,
        }

    if tool_name == "launch_app":
        return {
            "action": "launch_app",
            "coordinates": [],
            "type_information": normalized_args["app_name"],
            "screen_index": 0,
            "end_screen_index": 0,
        }

    if tool_name == "open_app_launcher":
        return {
            "action": "open_app_launcher",
            "coordinates": [],
            "type_information": "",
            "screen_index": 0,
            "end_screen_index": 0,
        }

    if tool_name == "open_in_browser":
        return {
            "action": "open_in_browser",
            "coordinates": [],
            "type_information": normalized_args.get("url") or normalized_args.get("query", ""),
            "screen_index": 0,
            "end_screen_index": 0,
        }

    if tool_name == "open_in_finder":
        return {
            "action": "open_in_finder",
            "coordinates": [],
            "type_information": normalized_args.get("path", ""),
            "screen_index": 0,
            "end_screen_index": 0,
        }

    if tool_name == "manage_files":
        mode = normalized_args.get("mode", "list")
        type_info_parts = [mode]
        if mode == "list":
            type_info_parts.append(normalized_args.get("path", ""))
        elif mode == "search":
            type_info_parts.append(normalized_args.get("path", ""))
            type_info_parts.append(normalized_args.get("query", ""))
        elif mode == "delete":
            type_info_parts.append(",".join(normalized_args.get("paths", [])))
        elif mode == "create":
            type_info_parts.append(normalized_args.get("parent", ""))
            type_info_parts.append(",".join(i["name"] for i in normalized_args.get("items", [])))
        elif mode == "move":
            type_info_parts.append(normalized_args.get("source", ""))
            type_info_parts.append(normalized_args.get("destination", ""))
        elif mode == "rename":
            type_info_parts.append(normalized_args.get("path", ""))
            type_info_parts.append(normalized_args.get("new_name", ""))
        return {
            "action": "manage_files",
            "coordinates": [],
            "type_information": "|".join(type_info_parts),
            "screen_index": 0,
            "end_screen_index": 0,
        }

    if tool_name == "read_current_page":
        return {
            "action": "read_current_page",
            "coordinates": [],
            "type_information": "",
            "screen_index": 0,
            "end_screen_index": 0,
        }

    if tool_name == "read_current_document":
        if normalized_args.get("mode") != "extract" or "position" not in normalized_args:
            return {
                "action": "read_current_document",
                "coordinates": [],
                "type_information": "",
                "screen_index": 0,
                "end_screen_index": 0,
            }
        return {
            "action": "read_current_document",
            "coordinates": normalized_args["position"],
            "type_information": "",
            "screen_index": normalized_args["screen_index"],
            "end_screen_index": normalized_args["screen_index"],
        }

    if tool_name == "hold_modifier_keys":
        return {
            "action": "hold_modifier_keys",
            "coordinates": [],
            "type_information": " ".join(normalized_args["keys"]),
            "screen_index": 0,
            "end_screen_index": 0,
        }

    if tool_name == "release_modifier_keys":
        return {
            "action": "release_modifier_keys",
            "coordinates": [],
            "type_information": " ".join(normalized_args.get("keys", [])),
            "screen_index": 0,
            "end_screen_index": 0,
        }

    if tool_name == "input_text":
        coordinates = normalized_args.get("position", [0, 0])
        screen_index = normalized_args.get("screen_index", 0)
        return {
            "action": "input_text",
            "coordinates": coordinates,
            "type_information": normalized_args["text"],
            "screen_index": screen_index,
            "end_screen_index": screen_index,
        }

    if tool_name == "remember":
        return {
            "action": "remember",
            "coordinates": [0, 0],
            "type_information": normalized_args["content"],
            "screen_index": 0,
            "end_screen_index": 0,
        }

    if tool_name == "code_agent":
        return {
            "action": "code_agent",
            "coordinates": [],
            "type_information": normalized_args["task"],
            "screen_index": 0,
            "end_screen_index": 0,
        }

    if tool_name == "stop_code_agent":
        return {
            "action": "stop_code_agent",
            "coordinates": [],
            "type_information": normalized_args["job_id"],
            "screen_index": 0,
            "end_screen_index": 0,
        }

    raise ValueError(f"未知工具: {tool_name}")


def extract_tool_points(tool_name: str, tool_args: Dict[str, Any]) -> List[Tuple[float, float]]:
    normalized_args = normalize_tool_args(tool_name, tool_args)
    if tool_name == "drag":
        return [
            tuple(normalized_args["start_position"]),
            tuple(normalized_args["end_position"]),
        ]
    if "position" in normalized_args:
        return [tuple(normalized_args["position"])]
    return []


def comparable_tool_args(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    normalized_args = normalize_tool_args(tool_name, tool_args)
    comparable: Dict[str, Any] = {}
    for key, value in normalized_args.items():
        if key.endswith("position"):
            continue
        comparable[key] = value
    return comparable
