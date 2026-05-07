"""
记忆管理模块

提供AI对话记忆的统一管理功能，支持文本和图片记忆。
"""

import base64
import copy
import json
import os
import time
from typing import Any, Dict, List, Optional, Union

import cv2

from baodou_ai.agent.protocol import normalize_agent_response


class MemoryManager:
    """记忆管理器"""
    
    MAX_TEXT_MEMORY = 25
    MAX_IMAGE_MEMORY = 3
    
    def __init__(self, config=None):
        self._config = config
        self._messages: List[Dict] = []
        self._image_group_count = 0
        self._image_cache: Dict[str, str] = {}
        self._max_text_memory = self.MAX_TEXT_MEMORY
        self._max_image_memory = self.MAX_IMAGE_MEMORY
        self._load_memory_limits_from_config()
    
    def _load_memory_limits_from_config(self) -> None:
        memory_config = {}
        
        if self._config is not None:
            if hasattr(self._config, "memory_config"):
                memory_config = getattr(self._config, "memory_config") or {}
            elif isinstance(self._config, dict):
                memory_config = self._config.get("memory_config", {})
        
        self._max_text_memory = self._normalize_positive_int(
            memory_config.get("max_text_memory"),
            self.MAX_TEXT_MEMORY
        )
        self._max_image_memory = self._normalize_positive_int(
            memory_config.get("max_image_memory"),
            self.MAX_IMAGE_MEMORY
        )
    
    @staticmethod
    def _normalize_positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
            return parsed if parsed > 0 else default
        except (TypeError, ValueError):
            return default
    
    def clear(self) -> None:
        """清空所有记忆"""
        self._messages = []
        self._image_group_count = 0
        self._image_cache = {}
        print("已清空所有记忆")

    @staticmethod
    def _normalize_data_url(value: str) -> str:
        """统一图片 data URL 格式"""
        if value.startswith("data:image"):
            return value
        return f"data:image/png;base64,{value}"

    @staticmethod
    def _clone_content_items(content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """克隆多模态消息内容，避免历史投影与当前内容互相污染。"""
        return copy.deepcopy(content)

    def add_user_capture(
        self,
        captures: List[Any],
        text: str,
        history_text: Optional[str] = None,
    ) -> None:
        """添加内存中的截图组，避免落盘后二次编码"""
        content: List[Dict[str, Any]] = []
        valid_image_count = 0

        for i, capture in enumerate(captures):
            if isinstance(capture, dict):
                screen_index = int(capture.get("index", i))
                frame_hash = capture.get("frame_hash")
                data_url = capture.get("data_url")
            else:
                screen_index = int(getattr(capture, "index", i))
                frame_hash = getattr(capture, "frame_hash", None)
                data_url = getattr(capture, "data_url", None)

            if not data_url and frame_hash:
                data_url = self._image_cache.get(frame_hash)

            if not data_url:
                continue

            normalized_url = self._normalize_data_url(data_url)
            if frame_hash:
                self._image_cache[frame_hash] = normalized_url

            content.append({"type": "text", "text": f"[Screen {screen_index}]"})
            content.append({
                "type": "image_url",
                "image_url": {"url": normalized_url}
            })
            valid_image_count += 1

        full_content = self._clone_content_items(content)
        full_content.append({"type": "text", "text": text})

        history_content = None
        if history_text is not None:
            history_content = self._clone_content_items(content)
            history_content.append({"type": "text", "text": history_text})

        message = {
            "role": "user",
            "content": full_content,
            "timestamp": time.time(),
            "image_count": valid_image_count,
            "is_initial": not any(m.get("is_initial") for m in self._messages if m.get("role") == "user"),
        }
        if history_content is not None:
            message["history_content"] = history_content

        self._messages.append(message)

        if valid_image_count > 0:
            self._image_group_count += 1

        self._cleanup_images()
        self._cleanup_messages()
    
    def add_user_message(
        self,
        image_paths: Union[str, List[str]],
        text: str,
        history_text: Optional[str] = None,
    ) -> None:
        """
        添加用户消息（包含图片和文本）
        
        Args:
            image_paths: 图片路径（单个路径或路径列表）
            text: 用户文本内容
        """
        if isinstance(image_paths, str):
            image_paths = [image_paths]
        
        content = []
        valid_image_count = 0
        
        for i, image_path in enumerate(image_paths):
            image_data = self._encode_image(image_path)
            if image_data:
                content.append({
                    "type": "text",
                    "text": f"[Screen {i}]"
                })
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image_data}
                })
                valid_image_count += 1
            else:
                print(f"无法读取图片: {image_path}")
        
        if valid_image_count == 0:
            print("没有有效的图片，仅添加文本消息")

        full_content = self._clone_content_items(content)
        full_content.append({"type": "text", "text": text})

        history_content = None
        if history_text is not None:
            history_content = self._clone_content_items(content)
            history_content.append({"type": "text", "text": history_text})

        message = {
            "role": "user",
            "content": full_content,
            "timestamp": time.time(),
            "image_count": valid_image_count,
            "is_initial": not any(m.get("is_initial") for m in self._messages if m.get("role") == "user"),
        }
        if history_content is not None:
            message["history_content"] = history_content
        
        self._messages.append(message)
        
        if valid_image_count > 0:
            self._image_group_count += 1
        
        self._cleanup_images()
        self._cleanup_messages()
    
    def add_assistant_message(
        self,
        content: str,
        action_feedback: str = "",
        parsed_response: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        添加AI助手消息
        
        Args:
            content: AI返回的原始内容
            action_feedback: 操作反馈信息
            parsed_response: 解析后的结构化响应
        """
        full_content = self._summarize_assistant_message(parsed_response, content)
        if False and action_feedback:
            feedback_summary = self._summarize_feedback(action_feedback)
            full_content = f"{full_content}\n\n[操作反馈]: {feedback_summary}"
        
        if not full_content:
            print("assistant 响应未能归一为 JSON，跳过 assistant 记忆写入")
            return

        message = {
            "role": "assistant",
            "content": full_content,
            "timestamp": time.time()
        }
        
        self._messages.append(message)
        self._cleanup_messages()

    def _summarize_assistant_message(
        self,
        parsed_response: Optional[Dict[str, Any]],
        raw_content: str
    ) -> str:
        """用结构化短文本代替完整原始响应，控制上下文膨胀"""
        if not parsed_response:
            return ""

        try:
            normalized_response = normalize_agent_response(parsed_response)
            return json.dumps(normalized_response, ensure_ascii=False, indent=2)
        except Exception:
            screen_index = self._normalize_int(parsed_response.get("screen_index"), 0)
            normalized_response = {
                "thinking": str(parsed_response.get("thinking", "")),
                "whether_completed": self._normalize_completion_status(
                    parsed_response.get("whether_completed")
                ),
                "screen_index": screen_index,
                "end_screen_index": self._normalize_int(
                    parsed_response.get("end_screen_index"),
                    screen_index,
                ),
                "element_info": str(parsed_response.get("element_info", "")),
                "coordinates": self._normalize_coordinates(parsed_response.get("coordinates")),
                "action": str(parsed_response.get("action", "")),
                "type_information": str(parsed_response.get("type_information", "")),
            }

        return json.dumps(normalized_response, ensure_ascii=False, indent=2)

    @staticmethod
    def _normalize_completion_status(value: Any) -> str:
        """统一 whether_completed 的字面量"""
        if value == "difficult":
            return "difficult"
        if value in (True, "True"):
            return "True"
        return "False"

    @staticmethod
    def _normalize_int(value: Any, default: int) -> int:
        """统一屏幕索引为整数"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _normalize_coordinates(self, value: Any) -> List[Any]:
        """将坐标字段标准化为 JSON 数组"""
        if isinstance(value, list):
            return value

        if isinstance(value, tuple):
            return list(value)

        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        return [0, 0]

    @staticmethod
    def _summarize_feedback(feedback: str) -> str:
        """压缩系统反馈，避免上下文无限增长"""
        raw = str(feedback or "")
        if not raw.strip():
            return ""

        looks_like_listing = ("📄" in raw) or ("📁" in raw) or ("共找到" in raw and "\n" in raw)
        looks_like_document_content = (
            "--- Document Content" in raw
            or "--- Page Content" in raw
        )
        if looks_like_listing or looks_like_document_content:
            max_lines = 2000
            lines = [line.rstrip() for line in raw.splitlines() if line.strip()]
            if len(lines) > max_lines:
                remaining = len(lines) - max_lines
                lines = lines[:max_lines]
                lines.append(f"...（后续 {remaining} 行已截断）")
            summarized = "\n".join(lines)
            return summarized

        normalized = " ".join(raw.split())
        return normalized[:400]
    
    def add_feedback_only(self, feedback: str) -> None:
        """
        添加纯反馈消息（用户角色的系统反馈）
        
        Args:
            feedback: 反馈内容
        """
        feedback_text = self._summarize_feedback(feedback)
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": f"[System Feedback]: {feedback_text}"}
            ],
            "timestamp": time.time(),
            "is_feedback": True
        }
        
        self._messages.append(message)
        self._cleanup_messages()
    
    def _encode_image(self, image_path: str) -> Optional[str]:
        """将图片编码为base64"""
        try:
            if not os.path.exists(image_path):
                return None
            
            img = cv2.imread(image_path)
            if img is None:
                return None
            
            _, buffer = cv2.imencode(".png", img)
            img_base64 = base64.b64encode(buffer).decode("utf-8")
            
            return f"data:image/png;base64,{img_base64}"
        except Exception as e:
            print(f"图片编码失败: {e}")
            return None
    
    def _cleanup_images(self) -> None:
        """清理多余的图片记忆，优先移除非首轮的图片消息"""
        image_messages = []
        
        for msg in self._messages:
            if msg.get("role") == "user" and self._has_image(msg):
                image_messages.append(msg)
        
        if len(image_messages) > self._max_image_memory:
            groups_to_remove = len(image_messages) - self._max_image_memory
            removed_groups = 0
            
            new_messages = []
            for msg in self._messages:
                if msg.get("role") == "user" and self._has_image(msg):
                    if removed_groups < groups_to_remove and not msg.get("is_initial"):
                        new_messages.append(self._strip_images_from_message(msg))
                        removed_groups += 1
                    elif removed_groups < groups_to_remove:
                        new_messages.append(self._strip_images_from_message(msg))
                        removed_groups += 1
                    else:
                        new_messages.append(msg)
                else:
                    new_messages.append(msg)
            
            self._messages = new_messages
            self._image_group_count = self._max_image_memory
    
    def _cleanup_messages(self) -> None:
        """清理多余的消息，优先保留首轮 user message"""
        if len(self._messages) <= self._max_text_memory * 2:
            return

        initial_indices = set()
        for idx, msg in enumerate(self._messages):
            if msg.get("role") == "user" and msg.get("is_initial"):
                initial_indices.add(idx)

        non_initial_messages = [(idx, msg) for idx, msg in enumerate(self._messages) if idx not in initial_indices]
        initial_messages = [(idx, msg) for idx, msg in enumerate(self._messages) if idx in initial_indices]

        target_count = self._max_text_memory * 2
        while len(self._messages) > target_count and non_initial_messages:
            non_initial_messages.pop(0)
            self._messages = [msg for _, msg in non_initial_messages] + [msg for _, msg in initial_messages]
            self._messages.sort(key=lambda m: m.get("timestamp", 0))

        if len(self._messages) > target_count:
            recent_messages = self._messages[-(target_count):]
            self._messages = recent_messages
    
    def _has_image(self, message: Dict) -> bool:
        """检查消息是否包含图片"""
        content = message.get("content", [])
        if isinstance(content, list):
            for item in content:
                if item.get("type") == "image_url":
                    return True
        return False
    
    def _strip_images_from_message(self, message: Dict) -> Dict:
        """从消息中移除所有图片，保留文本"""
        def strip_content_items(content: Any) -> Any:
            if not isinstance(content, list):
                return content

            screen_indices = []
            new_content = []
            for item in content:
                if item.get("type") == "image_url":
                    continue
                if item.get("type") == "text":
                    text = item.get("text", "")
                    if text.startswith("[Screen ") and "]" in text:
                        try:
                            idx = int(text.replace("[Screen ", "").replace("]", ""))
                            screen_indices.append(idx)
                            continue
                        except Exception:
                            pass
                new_content.append(item)

            if not new_content:
                if screen_indices:
                    screens_str = ", ".join([f"Screen {i}" for i in screen_indices])
                    return [{"type": "text", "text": f"[Images removed: {screens_str}]"}]
                return [{"type": "text", "text": "[Images removed]"}]

            return new_content

        message = message.copy()
        message["content"] = strip_content_items(message.get("content", []))
        if "history_content" in message:
            message["history_content"] = strip_content_items(message.get("history_content", []))
        message["image_count"] = 0
        return message
    
    def get_messages(self, system_prompt: str = "", latest_user_full: bool = False) -> List[Dict]:
        """
        获取完整的消息列表，用于API调用
        
        Args:
            system_prompt: 系统提示词
        
        Returns:
            格式化的消息列表
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        last_message_index = len(self._messages) - 1
        for index, msg in enumerate(self._messages):
            content = msg["content"]
            if (
                msg.get("role") == "user"
                and "history_content" in msg
                and not (latest_user_full and index == last_message_index)
            ):
                content = msg["history_content"]
            clean_msg = {
                "role": msg["role"],
                "content": content
            }
            messages.append(clean_msg)
        
        return messages
    
    def get_last_n_messages(self, n: int = 5) -> List[Dict]:
        """获取最近n条消息"""
        return self._messages[-n:] if self._messages else []
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """获取记忆摘要"""
        image_group_count = sum(1 for msg in self._messages if msg.get("role") == "user" and self._has_image(msg))
        total_image_count = sum(
            msg.get("image_count", 0) 
            for msg in self._messages 
            if msg.get("role") == "user" and self._has_image(msg)
        )
        return {
            "total_messages": len(self._messages),
            "image_group_count": image_group_count,
            "total_image_count": total_image_count,
            "user_messages": sum(1 for msg in self._messages if msg["role"] == "user"),
            "assistant_messages": sum(1 for msg in self._messages if msg["role"] == "assistant"),
        }
