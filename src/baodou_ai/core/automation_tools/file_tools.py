"""Finder/file-management automation tools."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .runtime import ToolContext, ToolInterrupted, ToolOutcome


class FileToolsMixin:
    _FINDER_APP_NAMES = ("Finder", "访达")
    _EXPLORER_APP_NAMES = ("File Explorer", "Windows Explorer", "Explorer", "资源管理器")
    _FILE_MANAGER_APP_NAMES = _FINDER_APP_NAMES + _EXPLORER_APP_NAMES

    def _is_supported_file_manager_app(self, app_name: str) -> bool:
        return str(app_name or "").strip() in self._FILE_MANAGER_APP_NAMES

    def _check_finder_frontmost(self) -> Optional[str]:
        try:
            info = self.get_frontmost_app_info()
            app_name = str(info.get("app_name") or "").strip()
            if self._is_supported_file_manager_app(app_name):
                return None
            return (
                "当前前台应用不是访达或文件资源管理器，manage_files 工具仅在前台窗口是文件管理器时可用。"
                "你可以先调用 open_in_finder 打开目标文件夹，再尝试使用此工具。"
            )
        except Exception:
            return "无法判断当前前台应用，manage_files 工具仅在前台窗口是访达或文件资源管理器时可用。"

    def _get_active_file_manager_path(self) -> Optional[str]:
        for name in self._FILE_MANAGER_APP_NAMES:
            result = self._platform_adapter.get_active_document_path(name)
            if result:
                return result
        return None

    def tool_manage_files(
        self,
        mode: str = "list",
        path: Optional[str] = None,
        query: Optional[str] = None,
        paths: Optional[List[str]] = None,
        parent: Optional[str] = None,
        items: Optional[List[Dict[str, str]]] = None,
        source: Optional[str] = None,
        destination: Optional[str] = None,
        new_name: Optional[str] = None,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        try:
            return self._tool_manage_files_interruptible(
                mode=mode,
                path=path,
                query=query,
                paths=paths,
                parent=parent,
                items=items,
                source=source,
                destination=destination,
                new_name=new_name,
                screen_info=screen_info,
                should_stop=should_stop,
            )
        except ToolInterrupted:
            return self._build_tool_result(False, self._INTERRUPTED_SUMMARY, self._INTERRUPTED_ERROR)

    def _tool_manage_files_interruptible(
        self,
        mode: str = "list",
        path: Optional[str] = None,
        query: Optional[str] = None,
        paths: Optional[List[str]] = None,
        parent: Optional[str] = None,
        items: Optional[List[Dict[str, str]]] = None,
        source: Optional[str] = None,
        destination: Optional[str] = None,
        new_name: Optional[str] = None,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        self._raise_if_stopped(should_stop)
        frontmost_error = self._check_finder_frontmost()
        if frontmost_error:
            return {"ok": False, "summary": frontmost_error, "error": frontmost_error}

        context = self._build_tool_context(screen_info)

        def operation(_context: ToolContext) -> ToolOutcome:
            normalized_mode = str(mode or "list").strip().lower()

            if normalized_mode == "list":
                return self._manage_files_list(path or self._get_active_file_manager_path(), should_stop=should_stop)
            if normalized_mode == "search":
                return self._manage_files_search(path or self._get_active_file_manager_path(), query, should_stop=should_stop)
            if normalized_mode == "delete":
                return self._manage_files_delete(paths, should_stop=should_stop)
            if normalized_mode == "create":
                return self._manage_files_create(parent or self._get_active_file_manager_path(), items, should_stop=should_stop)
            if normalized_mode == "move":
                return self._manage_files_move(source, destination, should_stop=should_stop)
            if normalized_mode == "rename":
                return self._manage_files_rename(path, new_name, should_stop=should_stop)

            return self._build_tool_outcome(False, f"不支持的 mode: {normalized_mode}")

        return self._execute_tool_runtime(
            context=context,
            operation=operation,
            failure_summary="文件管理操作失败",
            should_stop=should_stop,
        )

    def _manage_files_list(
        self,
        target_path: Optional[str],
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> ToolOutcome:
        if not target_path:
            return self._build_tool_outcome(False, "未指定目录路径，且无法获取当前文件管理器窗口路径")
        dir_path = Path(target_path)
        if not dir_path.is_dir():
            return self._build_tool_outcome(False, f"路径不是有效目录: {target_path}")

        try:
            entries = sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return self._build_tool_outcome(False, f"无权限访问目录: {target_path}")

        lines = [f"目录: {target_path}", ""]
        folder_count = 0
        file_count = 0
        scanned_count = 0
        for entry in entries:
            if should_stop is not None and should_stop():
                return self._build_tool_outcome(
                    False,
                    f"工具执行已中断；已扫描 {scanned_count} 项。",
                    self._INTERRUPTED_ERROR,
                )
            scanned_count += 1
            try:
                stat = entry.stat()
                mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
                if entry.is_dir():
                    lines.append(f"📁 {entry.name}/  —  {mtime}")
                    folder_count += 1
                else:
                    size = stat.st_size
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    elif size < 1024 * 1024 * 1024:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    else:
                        size_str = f"{size / (1024 * 1024 * 1024):.1f} GB"
                    lines.append(f"📄 {entry.name}  {size_str}  —  {mtime}")
                    file_count += 1
            except (PermissionError, OSError):
                lines.append(f"❓ {entry.name}  —  (无法读取信息)")

        lines.append("")
        lines.append(f"共 {folder_count} 个文件夹, {file_count} 个文件")
        return self._build_tool_outcome(True, "\n".join(lines))

    def _manage_files_delete(
        self,
        paths: Optional[List[str]],
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> ToolOutcome:
        if not paths:
            return self._build_tool_outcome(False, "未提供要删除的路径")

        success_items = []
        skipped_items = []
        total = len(paths)
        for index, p in enumerate(paths):
            if should_stop is not None and should_stop():
                remaining = total - index
                return self._build_tool_outcome(
                    False,
                    f"工具执行已中断；已处理 {index} 项，剩余 {remaining} 项未处理。",
                    self._INTERRUPTED_ERROR,
                    processed_count=index,
                    remaining_count=remaining,
                    success_items=success_items,
                    skipped_items=skipped_items,
                )
            target = Path(p)
            if not target.exists():
                skipped_items.append(f"{p} (路径不存在)")
                continue
            try:
                result = self._platform_adapter.move_to_trash(p)
                if result.get("ok"):
                    success_items.append(p)
                else:
                    skipped_items.append(f"{p} ({result.get('error', '未知错误')})")
            except Exception as exc:
                skipped_items.append(f"{p} ({exc})")

        parts = []
        if success_items:
            parts.append(f"已移到废纸篓: {', '.join(success_items)}")
        if skipped_items:
            parts.append(f"跳过: {'; '.join(skipped_items)}")
        summary = "。".join(parts) if parts else "没有可操作的条目"
        return self._build_tool_outcome(True, summary)

    def _manage_files_create(
        self,
        parent_path: Optional[str],
        items: Optional[List[Dict[str, str]]],
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> ToolOutcome:
        if not parent_path:
            return self._build_tool_outcome(False, "未指定目标目录，且无法获取当前文件管理器窗口路径")
        if not items:
            return self._build_tool_outcome(False, "未提供要创建的条目")

        parent = Path(parent_path)
        if not parent.is_dir():
            return self._build_tool_outcome(False, f"目标目录不存在: {parent_path}")

        success_items = []
        skipped_items = []
        total = len(items)
        for index, item in enumerate(items):
            if should_stop is not None and should_stop():
                remaining = total - index
                return self._build_tool_outcome(
                    False,
                    f"工具执行已中断；已处理 {index} 项，剩余 {remaining} 项未处理。",
                    self._INTERRUPTED_ERROR,
                    processed_count=index,
                    remaining_count=remaining,
                    success_items=success_items,
                    skipped_items=skipped_items,
                )
            name = item.get("name", "")
            item_type = item.get("type", "file")
            target = parent / name
            if target.exists():
                skipped_items.append(f"{name} (已存在)")
                continue
            try:
                if item_type == "folder":
                    target.mkdir(parents=True, exist_ok=False)
                    success_items.append(f"{name}/ (文件夹)")
                else:
                    target.touch()
                    success_items.append(f"{name} (文件)")
            except Exception as exc:
                skipped_items.append(f"{name} ({exc})")

        parts = []
        if success_items:
            parts.append(f"已创建: {', '.join(success_items)}")
        if skipped_items:
            parts.append(f"跳过: {'; '.join(skipped_items)}")
        summary = "。".join(parts) if parts else "没有可操作的条目"
        return self._build_tool_outcome(True, summary)

    def _manage_files_move(
        self,
        source_path: Optional[str],
        dest_path: Optional[str],
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> ToolOutcome:
        if not source_path:
            return self._build_tool_outcome(False, "未提供 source 路径")
        if not dest_path:
            return self._build_tool_outcome(False, "未提供 destination 路径")

        source = Path(source_path)
        dest_dir = Path(dest_path)

        if not source.exists():
            return self._build_tool_outcome(False, f"源路径不存在: {source_path}")
        if not dest_dir.is_dir():
            return self._build_tool_outcome(False, f"目标目录不存在: {dest_path}")

        target = dest_dir / source.name
        if target.exists():
            return self._build_tool_outcome(False, f"目标位置已存在同名条目: {target}")

        self._raise_if_stopped(should_stop)
        try:
            shutil.move(str(source), str(dest_dir))
            return self._build_tool_outcome(True, f"已将 {source.name} 移动到 {dest_path}")
        except Exception as exc:
            return self._build_tool_outcome(False, f"移动失败: {exc}")

    _MANAGE_FILES_SEARCH_MAX_RESULTS = 50

    def _manage_files_search(
        self,
        target_path: Optional[str],
        query: Optional[str],
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> ToolOutcome:
        if not target_path:
            return self._build_tool_outcome(False, "未指定搜索目录，且无法获取当前文件管理器窗口路径")
        if not query:
            return self._build_tool_outcome(False, "未提供搜索词 query")
        dir_path = Path(target_path)
        if not dir_path.is_dir():
            return self._build_tool_outcome(False, f"路径不是有效目录: {target_path}")

        lowered_query = query.strip().lower()
        if not lowered_query:
            return self._build_tool_outcome(False, "搜索词不能为空")

        matches: List[str] = []
        scanned_count = 0
        try:
            for root, dirs, files in os.walk(dir_path):
                if should_stop is not None and should_stop():
                    return self._build_tool_outcome(
                        False,
                        f"工具执行已中断；已扫描 {scanned_count} 项，已找到 {len(matches)} 个结果。",
                        self._INTERRUPTED_ERROR,
                        scanned_count=scanned_count,
                        result_count=len(matches),
                        search_results=matches,
                    )
                for name in dirs + files:
                    if should_stop is not None and should_stop():
                        return self._build_tool_outcome(
                            False,
                            f"工具执行已中断；已扫描 {scanned_count} 项，已找到 {len(matches)} 个结果。",
                            self._INTERRUPTED_ERROR,
                            scanned_count=scanned_count,
                            result_count=len(matches),
                            search_results=matches,
                        )
                    scanned_count += 1
                    if lowered_query in name.lower():
                        full_path = str(Path(root) / name)
                        entry = Path(full_path)
                        try:
                            if entry.is_dir():
                                matches.append(f"📁 {full_path}/")
                            else:
                                matches.append(f"📄 {full_path}")
                        except (PermissionError, OSError):
                            matches.append(f"❓ {full_path}")
                        if len(matches) >= self._MANAGE_FILES_SEARCH_MAX_RESULTS:
                            break
                if len(matches) >= self._MANAGE_FILES_SEARCH_MAX_RESULTS:
                    break
        except PermissionError:
            return self._build_tool_outcome(False, f"无权限访问目录: {target_path}")

        if not matches:
            return self._build_tool_outcome(True, f"在 {target_path} 及其子目录中未找到包含「{query}」的文件或文件夹")

        lines = [f"搜索目录: {target_path}", f"搜索词: {query}", ""]
        lines.extend(matches)
        truncated = len(matches) >= self._MANAGE_FILES_SEARCH_MAX_RESULTS
        lines.append("")
        count_line = f"共找到 {len(matches)} 个结果"
        if truncated:
            count_line += f"（已达上限 {self._MANAGE_FILES_SEARCH_MAX_RESULTS}，可能还有更多）"
        lines.append(count_line)
        return self._build_tool_outcome(True, "\n".join(lines))

    def _manage_files_rename(
        self,
        target_path: Optional[str],
        new_name: Optional[str],
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> ToolOutcome:
        if not target_path:
            return self._build_tool_outcome(False, "未提供 path 路径")
        if not new_name:
            return self._build_tool_outcome(False, "未提供 new_name")

        source = Path(target_path)
        if not source.exists():
            return self._build_tool_outcome(False, f"路径不存在: {target_path}")

        target = source.parent / new_name
        if target.exists():
            return self._build_tool_outcome(False, f"目标名称已存在: {new_name}")

        self._raise_if_stopped(should_stop)
        try:
            source.rename(target)
            return self._build_tool_outcome(True, f"已将 {source.name} 重命名为 {new_name}")
        except Exception as exc:
            return self._build_tool_outcome(False, f"重命名失败: {exc}")
