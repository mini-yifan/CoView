"""Pydantic schemas for the agent protocol and GUI tool arguments."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator


ToolArgs = Dict[str, Any]


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _validation_error_to_value_error(exc: ValidationError) -> ValueError:
    errors = exc.errors()
    if not errors:
        return ValueError(str(exc))
    message = str(errors[0].get("msg") or str(exc))
    if message.startswith("Value error, "):
        message = message[len("Value error, "):]
    return ValueError(message)


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
        number = _normalize_float(item, f"{field_name}[{index}]")
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
    return any(
        resolved_path == prefix or resolved_path.startswith(prefix + "/")
        for prefix in PATH_BLACKLIST
    )


def _resolve_safe_path(value: Any, field_name: str, *, allow_empty: bool = False) -> Optional[str]:
    path_text = _normalize_text(value, field_name).strip()
    if not path_text:
        if allow_empty:
            return None
        raise ValueError(f"{field_name} 不能为空字符串")
    try:
        resolved = str(Path(path_text).expanduser().resolve())
    except Exception as exc:
        raise ValueError(f"{field_name} 路径无效: {exc}") from exc
    if _is_path_blacklisted(resolved):
        raise ValueError(f"不允许访问系统敏感路径: {resolved}")
    return resolved


class ClickArgs(SchemaModel):
    screen_index: int
    position: List[float]

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        args = dict(data or {})
        return {
            "screen_index": _normalize_int(args.get("screen_index", 0), "screen_index"),
            "position": _normalize_position(args.get("position"), "position"),
        }


class LongPressArgs(ClickArgs):
    duration_seconds: float = 3.0

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        args = dict(data or {})
        normalized = ClickArgs.normalize(args)
        duration_seconds = _normalize_float(args.get("duration_seconds", 3), "duration_seconds")
        if duration_seconds < 1 or duration_seconds > 10:
            raise ValueError("duration_seconds 必须在 1-10 秒之间")
        normalized["duration_seconds"] = duration_seconds
        return normalized


class ScrollArgs(ClickArgs):
    scroll_level: int

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        args = dict(data or {})
        if "multiplier" in args:
            raise ValueError("滚动工具已改用 scroll_level 参数，不再接受 multiplier")
        normalized = ClickArgs.normalize(args)
        scroll_level = _normalize_int(args.get("scroll_level", 5), "scroll_level")
        if scroll_level < 1 or scroll_level > 10:
            raise ValueError("scroll_level 必须在 1-10 之间")
        normalized["scroll_level"] = scroll_level
        return normalized


class DragArgs(SchemaModel):
    start_screen_index: int
    start_position: List[float]
    end_screen_index: int
    end_position: List[float]

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        args = dict(data or {})
        return {
            "start_screen_index": _normalize_int(args.get("start_screen_index", 0), "start_screen_index"),
            "start_position": _normalize_position(args.get("start_position"), "start_position"),
            "end_screen_index": _normalize_int(args.get("end_screen_index", 0), "end_screen_index"),
            "end_position": _normalize_position(args.get("end_position"), "end_position"),
        }


class HotkeyArgs(SchemaModel):
    keys: List[str]

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        args = dict(data or {})
        return {"keys": _normalize_keys(args.get("keys"))}


class EmptyArgs(SchemaModel):
    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError("参数必须是对象")
        return {}


class PageLoadingArgs(SchemaModel):
    mode: str = "short_wait"
    wait_seconds: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        if data is None:
            return {"mode": "short_wait"}
        if not isinstance(data, dict):
            raise ValueError("page_loading 的参数必须是对象")
        if not data:
            return {"mode": "short_wait"}

        extra_keys = sorted(set(data.keys()) - {"mode", "wait_seconds"})
        if extra_keys:
            raise ValueError(f"page_loading 不支持的字段: {', '.join(extra_keys)}")

        mode = str(data.get("mode") or "short_wait").strip().lower()
        if mode not in {"short_wait", "long_wait"}:
            raise ValueError("page_loading.mode 只能是 short_wait 或 long_wait")

        if mode == "short_wait":
            return {"mode": "short_wait"}

        wait_seconds_raw = data.get("wait_seconds", 3)
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


class InputTextArgs(SchemaModel):
    text: str
    replace: bool = False
    submit: bool = False
    screen_index: Optional[int] = None
    position: Optional[List[float]] = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        args = dict(data or {})
        text = _normalize_text(args.get("text"), "text")
        has_screen_index = "screen_index" in args and args.get("screen_index") is not None
        has_position = "position" in args and args.get("position") is not None
        replace = _normalize_bool(args.get("replace", False), "replace")
        submit = _normalize_bool(args.get("submit", False), "submit")
        if has_screen_index != has_position:
            raise ValueError("input_text 传入坐标时必须同时提供 screen_index 和 position")
        normalized: ToolArgs = {
            "text": text,
            "replace": replace,
            "submit": submit,
        }
        if has_screen_index and has_position:
            normalized["screen_index"] = _normalize_int(args.get("screen_index", 0), "screen_index")
            normalized["position"] = _normalize_position(args.get("position"), "position")
        if replace and not (has_screen_index and has_position):
            raise ValueError("input_text(replace=true) 必须同时提供 screen_index 和 position")
        return normalized


class RememberArgs(SchemaModel):
    content: str

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("remember 必须是对象")
        extra_keys = sorted(set(data.keys()) - {"content"})
        if extra_keys:
            raise ValueError(f"remember 中存在不允许的字段: {', '.join(extra_keys)}")
        return {"content": _normalize_text(data.get("content"), "remember.content")}


class LaunchAppArgs(SchemaModel):
    app_name: str

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        args = dict(data or {})
        return {"app_name": _normalize_text(args.get("app_name"), "app_name")}


class OpenInBrowserArgs(SchemaModel):
    url: Optional[str] = None
    query: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        args = dict(data or {})
        has_url = "url" in args and args.get("url") is not None
        has_query = "query" in args and args.get("query") is not None
        if has_url == has_query:
            raise ValueError("open_in_browser 必须且只能提供 url 或 query 其中一个")
        if has_url:
            return {"url": _normalize_text(args.get("url"), "url")}
        return {"query": _normalize_text(args.get("query"), "query")}


class OpenInFinderArgs(SchemaModel):
    path: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError("open_in_finder 的参数必须是对象")
        raw_path = data.get("path")
        if raw_path is None:
            return {}
        resolved = _resolve_safe_path(raw_path, "path")
        return {"path": resolved}


class ReadCurrentPageArgs(SchemaModel):
    mode: str
    chunk_index: Optional[int] = None
    query: Optional[str] = None
    top_k: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        if data is None:
            return {"mode": "extract"}
        if not isinstance(data, dict):
            raise ValueError("read_current_page 的参数必须是对象")
        mode = _normalize_text(data.get("mode", "extract"), "mode").strip().lower()
        if mode not in {"extract", "chunk", "next", "search"}:
            raise ValueError('read_current_page.mode 只能是 "extract"、"chunk"、"next" 或 "search"')
        return _normalize_reader_args("read_current_page", mode, data)


class ReadCurrentDocumentArgs(SchemaModel):
    mode: str
    follow_view: bool = False
    screen_index: Optional[int] = None
    position: Optional[List[float]] = None
    chunk_index: Optional[int] = None
    query: Optional[str] = None
    top_k: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        if data is None:
            return {"mode": "extract", "follow_view": False}
        if not isinstance(data, dict):
            raise ValueError("read_current_document 的参数必须是对象")
        mode = _normalize_text(data.get("mode", "extract"), "mode").strip().lower()
        if mode not in {"extract", "chunk", "next", "search"}:
            raise ValueError('read_current_document.mode 只能是 "extract"、"chunk"、"next" 或 "search"')
        normalized = _normalize_reader_args("read_current_document", mode, data)
        normalized["follow_view"] = _normalize_bool(data.get("follow_view", False), "follow_view")
        has_screen_index = "screen_index" in data and data.get("screen_index") is not None
        has_position = "position" in data and data.get("position") is not None
        if mode == "extract":
            if has_screen_index != has_position:
                raise ValueError("read_current_document 传入坐标时必须同时提供 screen_index 和 position")
            if has_screen_index:
                normalized["screen_index"] = _normalize_int(data.get("screen_index", 0), "screen_index")
                normalized["position"] = _normalize_position(data.get("position"), "position")
            return normalized
        if has_screen_index or has_position:
            raise ValueError("read_current_document 的 chunk/next/search 模式不接受坐标")
        return normalized


def _normalize_reader_args(tool_name: str, mode: str, args: Dict[str, Any]) -> Dict[str, Any]:
    has_chunk_index = "chunk_index" in args and args.get("chunk_index") is not None
    has_query = "query" in args and args.get("query") is not None
    has_top_k = "top_k" in args and args.get("top_k") is not None
    normalized: ToolArgs = {"mode": mode}

    if mode == "extract":
        if has_chunk_index:
            raise ValueError(f"{tool_name}(mode=extract) 不接受 chunk_index")
        if has_query or has_top_k:
            raise ValueError(f"{tool_name}(mode=extract) 不接受 query 或 top_k")
        return normalized
    if mode == "chunk":
        if has_query or has_top_k:
            raise ValueError(f"{tool_name}(mode=chunk) 不接受 query 或 top_k")
        if not has_chunk_index:
            raise ValueError(f"{tool_name}(mode=chunk) 必须提供 chunk_index")
        normalized_chunk_index = _normalize_int(args.get("chunk_index"), "chunk_index")
        if normalized_chunk_index < 0:
            raise ValueError("chunk_index 必须是非负整数")
        normalized["chunk_index"] = normalized_chunk_index
        return normalized
    if mode == "next":
        if has_query or has_top_k:
            raise ValueError(f"{tool_name}(mode=next) 不接受 query 或 top_k")
        if has_chunk_index:
            raise ValueError(f"{tool_name}(mode=next) 不接受 chunk_index")
        return normalized
    if has_chunk_index:
        raise ValueError(f"{tool_name}(mode=search) 不接受 chunk_index")
    if not has_query:
        raise ValueError(f"{tool_name}(mode=search) 必须提供 query")
    normalized_query = _normalize_text(args.get("query"), "query").strip()
    if not normalized_query:
        raise ValueError(f"{tool_name}(mode=search) 必须提供非空 query")
    normalized["query"] = normalized_query
    normalized_top_k = _normalize_int(args.get("top_k", 3), "top_k")
    if normalized_top_k <= 0:
        raise ValueError("top_k 必须是正整数")
    normalized["top_k"] = normalized_top_k
    return normalized


class HoldModifierKeysArgs(SchemaModel):
    keys: List[str]

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        args = dict(data or {})
        return {"keys": _normalize_modifier_keys(args.get("keys"))}


class ReleaseModifierKeysArgs(SchemaModel):
    keys: Optional[List[str]] = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError("release_modifier_keys 的参数必须是对象")
        if "keys" not in data or data.get("keys") is None:
            return {}
        return {"keys": _normalize_modifier_keys(data.get("keys"))}


MANAGE_FILES_MAX_BATCH = 20


class ManageFilesArgs(SchemaModel):
    mode: str = "list"
    path: Optional[str] = None
    query: Optional[str] = None
    paths: Optional[List[str]] = None
    parent: Optional[str] = None
    items: Optional[List[Dict[str, str]]] = None
    source: Optional[str] = None
    destination: Optional[str] = None
    new_name: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        if data is None:
            return {"mode": "list"}
        if not isinstance(data, dict):
            raise ValueError("manage_files 的参数必须是对象")
        mode = _normalize_text(data.get("mode"), "mode").strip().lower()
        if mode not in ("list", "delete", "create", "move", "rename", "search"):
            raise ValueError(f"manage_files 的 mode 必须是 list/delete/create/move/rename/search 之一，收到: {mode}")
        result: ToolArgs = {"mode": mode}
        if mode in {"list", "search"}:
            raw_path = data.get("path")
            if raw_path is not None:
                resolved = _resolve_safe_path(raw_path, "path", allow_empty=True)
                if resolved:
                    result["path"] = resolved
            if mode == "search":
                raw_query = data.get("query")
                if not raw_query:
                    raise ValueError("search 模式必须提供 query 搜索词")
                result["query"] = _normalize_text(raw_query, "query").strip()
            return result
        if mode == "delete":
            raw_paths = data.get("paths")
            if not raw_paths or not isinstance(raw_paths, list):
                raise ValueError("delete 模式必须提供 paths 数组")
            if len(raw_paths) > MANAGE_FILES_MAX_BATCH:
                raise ValueError(f"单次最多删除 {MANAGE_FILES_MAX_BATCH} 个条目")
            result["paths"] = [_resolve_safe_path(p, "paths 中的路径") for p in raw_paths]
            return result
        if mode == "create":
            raw_parent = data.get("parent")
            if raw_parent is not None:
                resolved = _resolve_safe_path(raw_parent, "parent", allow_empty=True)
                if resolved:
                    result["parent"] = resolved
            raw_items = data.get("items")
            if not raw_items or not isinstance(raw_items, list):
                raise ValueError("create 模式必须提供 items 数组")
            if len(raw_items) > MANAGE_FILES_MAX_BATCH:
                raise ValueError(f"单次最多创建 {MANAGE_FILES_MAX_BATCH} 个条目")
            result["items"] = [_normalize_create_item(item) for item in raw_items]
            return result
        if mode == "move":
            if not data.get("source"):
                raise ValueError("move 模式必须提供 source 路径")
            if not data.get("destination"):
                raise ValueError("move 模式必须提供 destination 路径")
            result["source"] = _resolve_safe_path(data.get("source"), "source")
            result["destination"] = _resolve_safe_path(data.get("destination"), "destination")
            return result
        if mode == "rename":
            if not data.get("path"):
                raise ValueError("rename 模式必须提供 path 路径")
            if not data.get("new_name"):
                raise ValueError("rename 模式必须提供 new_name")
            result["path"] = _resolve_safe_path(data.get("path"), "path")
            new_name = _normalize_text(data.get("new_name"), "new_name").strip()
            if not new_name:
                raise ValueError("new_name 不能为空")
            if "/" in new_name or "\\" in new_name:
                raise ValueError(f"new_name 中不能包含路径分隔符: {new_name}")
            result["new_name"] = new_name
            return result
        return result


def _normalize_create_item(item: Any) -> Dict[str, str]:
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
    return {"name": name, "type": item_type}


class CodeAgentArgs(SchemaModel):
    task: str
    title: Optional[str] = None
    goal: Optional[str] = None
    job_id: Optional[str] = None
    workspace_path: Optional[str] = None
    timeout_seconds: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        if data is None or not isinstance(data, dict):
            raise ValueError("code_agent 的参数必须是对象")
        normalized: ToolArgs = {"task": _normalize_text(data.get("task"), "task")}
        for field in ("title", "goal"):
            if data.get(field) is not None:
                normalized[field] = _normalize_text(data.get(field), field)
        if data.get("job_id") is not None:
            job_id = _normalize_text(data.get("job_id"), "job_id").strip()
            if not job_id:
                raise ValueError("job_id 不能为空")
            normalized["job_id"] = job_id
        if data.get("workspace_path") is not None:
            workspace_path = _normalize_text(data.get("workspace_path"), "workspace_path").strip()
            if not workspace_path:
                raise ValueError("workspace_path 不能为空")
            normalized["workspace_path"] = str(Path(workspace_path).expanduser().resolve())
        if data.get("timeout_seconds") is not None:
            timeout_seconds = _normalize_int(data.get("timeout_seconds"), "timeout_seconds")
            if timeout_seconds <= 0:
                raise ValueError("timeout_seconds 必须是正整数")
            normalized["timeout_seconds"] = timeout_seconds
        return normalized


class StopCodeAgentArgs(SchemaModel):
    job_id: str

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        if data is None or not isinstance(data, dict):
            raise ValueError("stop_code_agent 的参数必须是对象")
        return {"job_id": _normalize_text(data.get("job_id"), "job_id")}


class RespondPayload(SchemaModel):
    outcome: str
    report: str

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("respond 必须是对象")
        extra_keys = sorted(set(data.keys()) - {"outcome", "report"})
        if extra_keys:
            raise ValueError(f"respond 中存在不允许的字段: {', '.join(extra_keys)}")
        outcome = _normalize_text(data.get("outcome"), "respond.outcome")
        if outcome not in {"completed", "needs_user"}:
            raise ValueError("respond.outcome 只能是 completed 或 needs_user")
        return {
            "outcome": outcome,
            "report": _normalize_text(data.get("report"), "respond.report"),
        }


TOOL_ARG_MODELS: Dict[str, Type[SchemaModel]] = {
    "click": ClickArgs,
    "double_click": ClickArgs,
    "long_press": LongPressArgs,
    "right_click": ClickArgs,
    "scroll_up": ScrollArgs,
    "scroll_down": ScrollArgs,
    "drag": DragArgs,
    "hotkey": HotkeyArgs,
    "page_loading": PageLoadingArgs,
    "launch_app": LaunchAppArgs,
    "open_app_launcher": EmptyArgs,
    "open_in_browser": OpenInBrowserArgs,
    "open_in_finder": OpenInFinderArgs,
    "manage_files": ManageFilesArgs,
    "read_current_page": ReadCurrentPageArgs,
    "read_current_document": ReadCurrentDocumentArgs,
    "hold_modifier_keys": HoldModifierKeysArgs,
    "release_modifier_keys": ReleaseModifierKeysArgs,
    "input_text": InputTextArgs,
    "remember": RememberArgs,
    "code_agent": CodeAgentArgs,
    "stop_code_agent": StopCodeAgentArgs,
}


def get_tool_args_model(name: str) -> Type[SchemaModel]:
    try:
        return TOOL_ARG_MODELS[name]
    except KeyError as exc:
        raise ValueError(f"未知工具: {name}") from exc


def normalize_tool_args_with_schema(name: str, args: Dict[str, Any] | None) -> ToolArgs:
    model_class = get_tool_args_model(str(name or "").strip())
    try:
        model = model_class.model_validate(args if args is not None else {})
    except ValidationError as exc:
        raise _validation_error_to_value_error(exc) from exc
    return model.model_dump(exclude_none=True)


def get_tool_json_schema(name: str) -> Dict[str, Any]:
    return get_tool_args_model(str(name or "").strip()).model_json_schema()


def normalize_remember_payload(value: Any) -> Dict[str, Any]:
    try:
        model = RememberArgs.model_validate(value)
    except ValidationError as exc:
        raise _validation_error_to_value_error(exc) from exc
    return model.model_dump(exclude_none=True)


def normalize_respond_payload(value: Any) -> Dict[str, Any]:
    try:
        model = RespondPayload.model_validate(value)
    except ValidationError as exc:
        raise _validation_error_to_value_error(exc) from exc
    return model.model_dump(exclude_none=True)


def normalize_page_loading_payload(value: Any) -> Dict[str, Any]:
    try:
        model = PageLoadingArgs.model_validate(value if value is not None else {})
    except ValidationError as exc:
        raise _validation_error_to_value_error(exc) from exc
    return model.model_dump(exclude_none=True)
