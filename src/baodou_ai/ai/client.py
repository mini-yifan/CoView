"""
AI客户端模块

提供与AI模型交互的功能，集成记忆管理系统。
"""

import base64
import os
import platform
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import cv2
from openai import OpenAI
from pydantic import BaseModel

from baodou_ai.agent.tool_registry import render_tool_prompt
from baodou_ai.core.config import Config
from baodou_ai.core.runtime_artifact_store import RuntimeArtifactStore
from baodou_ai.ai.prompt_builder import PromptBuilder
from baodou_ai.ai.parser import ResponseParser
from baodou_ai.ai.memory import MemoryManager
from baodou_ai.ai.runtime_prompt_context import RuntimePromptContext
from baodou_ai.platform import get_platform_adapter


class AIResponse(BaseModel):
    """AI响应数据模型"""
    thinking: str
    report: str = ""
    page_loading: Optional[Dict[str, Any]] = None
    remember: Optional[Dict[str, Any]] = None
    respond: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}


class AIClient:
    """AI模型客户端"""
    
    _instance: Optional["AIClient"] = None
    _PAGE_CONTEXT_MAX_CHARS = 4000
    
    def __new__(cls, config: Optional[Config] = None) -> "AIClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: Optional[Config] = None):
        if self._initialized:
            if config is not None:
                self._config = config
                self._memory = MemoryManager(config)
                self._default_browser_prompt_cache = None
                self._default_browser_prompt_loaded = False
            if not hasattr(self, "_prompt_builder"):
                self._prompt_builder = PromptBuilder()
            self._last_parse_error = ""
            self._last_parse_error_envelope = None
            return
        
        self._initialized = True
        self._config = config or Config()
        self._platform_adapter = get_platform_adapter()
        self._parser = ResponseParser()
        self._client: Optional[OpenAI] = None
        self._client_signature: Optional[Tuple[str, str, bool]] = None
        self._current_os = platform.system()
        self._prompt_cache: Optional[str] = None
        self._default_browser_prompt_cache: Optional[str] = None
        self._default_browser_prompt_loaded = False
        self._memory = MemoryManager(config)
        self._stream_usage_supported: Optional[bool] = None
        self._last_parse_error = ""
        self._last_parse_error_envelope: Optional[Dict[str, Any]] = None
        self._runtime_artifact_store = RuntimeArtifactStore()
        self._prompt_builder = PromptBuilder()
    
    def _get_client(self) -> OpenAI:
        """获取OpenAI客户端"""
        api_config = self._config.api_config
        tls_verify = bool(api_config.get("tls_verify", True))

        client_signature = (
            api_config.get("api_key", ""),
            api_config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            tls_verify,
        )
        if self._client is not None and self._client_signature == client_signature:
            return self._client

        self.close()
        import httpx

        self._client = OpenAI(
            api_key=client_signature[0],
            base_url=client_signature[1],
            http_client=httpx.Client(verify=tls_verify),
        )
        self._client_signature = client_signature
        return self._client
    
    def close(self) -> None:
        """关闭客户端连接"""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            finally:
                self._client = None
                self._client_signature = None
                self._stream_usage_supported = None
    
    def _read_image(self, image_path: str) -> Optional[str]:
        """读取图片并转换为base64"""
        try:
            img = cv2.imread(image_path)
            if img is None:
                raise Exception(f"无法读取图片: {image_path}")
            
            height, width, channels = img.shape
            print(f"成功读取图片: {image_path}")
            print(f"图片尺寸: {width} x {height} 像素")
            print(f"图片通道数: {channels}")
            
            _, buffer = cv2.imencode(".png", img)
            img_base64 = base64.b64encode(buffer).decode("utf-8")
            
            base_url = self._config.api_config.get("base_url", "")
            if base_url == "https://api.mindcraft.com.cn/v1/":
                return img_base64
            else:
                return f"data:image/png;base64,{img_base64}"
        
        except Exception as e:
            print(f"读取图片时出错: {e}")
            return None
    
    def _load_prompt(self) -> str:
        """加载系统提示词"""
        if self._prompt_cache is not None:
            return self._prompt_cache

        if self._current_os == "Darwin":
            prompt_file = "prompts/macos.txt"
        else:
            prompt_file = "prompts/windows.txt"
        
        prompt_path = self._platform_adapter.get_resource_path(prompt_file)
        
        if prompt_path and os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read().strip()
                tool_prompt = render_tool_prompt()
                if "{{GUI_TOOL_DEFINITIONS}}" in template:
                    self._prompt_cache = template.replace("{{GUI_TOOL_DEFINITIONS}}", tool_prompt)
                else:
                    self._prompt_cache = f"{template}\n\n{tool_prompt}"
                return self._prompt_cache
        
        prompts_dir = Path(__file__).parent / "prompts"
        prompt_file_path = prompts_dir / ("macos.txt" if self._current_os == "Darwin" else "windows.txt")
        
        if prompt_file_path.exists():
            with open(prompt_file_path, "r", encoding="utf-8") as f:
                template = f.read().strip()
                tool_prompt = render_tool_prompt()
                if "{{GUI_TOOL_DEFINITIONS}}" in template:
                    self._prompt_cache = template.replace("{{GUI_TOOL_DEFINITIONS}}", tool_prompt)
                else:
                    self._prompt_cache = f"{template}\n\n{tool_prompt}"
                return self._prompt_cache

        self._prompt_cache = ""
        return self._prompt_cache
    
    def clear_memory(self) -> None:
        """清空记忆"""
        self._memory.clear()
        self._last_parse_error = ""
        self._last_parse_error_envelope = None

    def set_runtime_artifact_store(self, store: RuntimeArtifactStore) -> None:
        """设置运行时产物存储入口（由 runner 注入）。"""
        self._runtime_artifact_store = store

    def get_last_parse_error(self) -> str:
        """返回最近一次模型输出解析失败原因；成功时为空字符串。"""
        return self._last_parse_error

    def get_last_parse_error_envelope(self) -> Optional[Dict[str, Any]]:
        """返回最近一次模型输出解析失败结构。"""
        return dict(self._last_parse_error_envelope or {}) if self._last_parse_error_envelope else None
    
    def add_feedback(self, feedback: str) -> None:
        """
        添加操作反馈到记忆
        
        Args:
            feedback: 操作反馈内容
        """
        self._memory.add_feedback_only(feedback)
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """获取记忆摘要"""
        return self._memory.get_memory_summary()

    def _build_full_user_content(
        self,
        user_content: str,
        runtime_context: Optional[RuntimePromptContext] = None,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        memory_content: str = "",
        page_context: Optional[Dict[str, Any]] = None,
        page_extraction_notice: str = "",
        document_context: Optional[Dict[str, Any]] = None,
        document_extraction_notice: str = "",
        context_warning_prompt: str = "",
        replan_feedback: str = "",
        process_report_mode: str = "auto",
        process_report_request_prompt: str = "",
        held_modifier_prompt: str = "",
        frontmost_app_prompt: str = "",
        background_jobs_prompt: str = "",
        pending_reports_prompt: str = "",
        respond_language_override: str = "",
    ) -> str:
        """构建当前轮发送给模型的文本内容"""
        context = runtime_context or RuntimePromptContext(
            screen_info=screen_info,
            memory_content=memory_content,
            page_context=page_context,
            page_extraction_notice=page_extraction_notice,
            document_context=document_context,
            document_extraction_notice=document_extraction_notice,
            context_warning_prompt=context_warning_prompt,
            replan_feedback=replan_feedback,
            process_report_mode=process_report_mode,
            process_report_request_prompt=process_report_request_prompt,
            held_modifier_prompt=held_modifier_prompt,
            frontmost_app_prompt=frontmost_app_prompt,
            background_jobs_prompt=background_jobs_prompt,
            pending_reports_prompt=pending_reports_prompt,
        )
        return self._prompt_builder.build_full_user_content(
            user_content=user_content,
            context=context,
            default_browser_prompt=self._build_default_browser_prompt(),
            respond_language=str(respond_language_override or "").strip() or self._config.get_respond_language(),
        )

    @staticmethod
    def _build_history_user_content(user_content: str) -> str:
        """为历史 user 消息保留最小必要的任务指令。"""
        return PromptBuilder.build_history_user_content(user_content)

    def _build_page_context_prompt(self, page_context: Optional[Dict[str, Any]]) -> str:
        return self._prompt_builder.build_page_context_prompt(page_context)

    def _build_document_context_prompt(self, document_context: Optional[Dict[str, Any]]) -> str:
        return self._prompt_builder.build_document_context_prompt(document_context)

    @classmethod
    def clear_context_debug_dir(cls) -> None:
        """兼容旧调用入口。"""
        RuntimeArtifactStore().clear_context_debug()

    def _write_context_debug_log(self, full_content: str, messages: List[Dict[str, Any]]) -> None:
        self._runtime_artifact_store.write_context_debug(full_content, messages)

    def _build_default_browser_prompt(self) -> str:
        """构建默认浏览器运行时上下文。"""
        if self._default_browser_prompt_loaded:
            return self._default_browser_prompt_cache or ""

        try:
            browser_info = self._platform_adapter.get_default_browser_info()
        except Exception as e:
            print(f"获取默认浏览器信息时出错: {e}")
            self._default_browser_prompt_loaded = True
            self._default_browser_prompt_cache = ""
            return ""

        app_name = str(browser_info.get("app_name", "")).strip()
        if not app_name:
            self._default_browser_prompt_loaded = True
            self._default_browser_prompt_cache = ""
            return ""

        self._default_browser_prompt_cache = (
            "[Default Browser]\n"
            f"Current default browser: {app_name}. "
            "When using open_in_browser(query=...), Chrome-based browsers use Google Search; others use Bing Search."
        )
        self._default_browser_prompt_loaded = True
        return self._default_browser_prompt_cache

    def _is_volcengine_base_url(self) -> bool:
        """判断当前 base_url 是否属于火山引擎兼容端点。"""
        base_url = (self._config.api_config.get("base_url", "") or "").strip().lower()
        if not base_url:
            return False

        parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
        hostname = (parsed.hostname or "").lower()
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in ("volces.com", "volcengine.com", "volcengineapi.com")
        )

    def _build_extra_body(self) -> Dict[str, Any]:
        """构造模型调用的 extra_body，并按平台兼容性附加可选字段。"""
        extra_body: Dict[str, Any] = {
            "thinking": {
                "type": self._config.ai_config.get("thinking_type", "disabled")
            }
        }

        reasoning_effort = self._config.ai_config.get("reasoning_effort", "minimal")
        if reasoning_effort and self._is_volcengine_base_url():
            extra_body["reasoning_effort"] = reasoning_effort

        return extra_body

    @staticmethod
    def _coerce_optional_int(value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _extract_usage_metrics(cls, usage: Any) -> Dict[str, Any]:
        if usage is None:
            return {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "cached_tokens": None,
                "reasoning_tokens": None,
                "token_usage_available": False,
            }

        if isinstance(usage, dict):
            getter = usage.get
        else:
            getter = lambda key, default=None: getattr(usage, key, default)

        prompt_tokens = cls._coerce_optional_int(getter("prompt_tokens"))
        completion_tokens = cls._coerce_optional_int(getter("completion_tokens"))
        total_tokens = cls._coerce_optional_int(getter("total_tokens"))
        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        prompt_details = getter("prompt_tokens_details")
        completion_details = getter("completion_tokens_details")
        if isinstance(prompt_details, dict):
            prompt_details_getter = prompt_details.get
        else:
            prompt_details_getter = lambda key, default=None: getattr(prompt_details, key, default)
        if isinstance(completion_details, dict):
            completion_details_getter = completion_details.get
        else:
            completion_details_getter = lambda key, default=None: getattr(completion_details, key, default)

        cached_tokens = cls._coerce_optional_int(prompt_details_getter("cached_tokens"))
        reasoning_tokens = cls._coerce_optional_int(completion_details_getter("reasoning_tokens"))
        token_usage_available = any(
            value is not None
            for value in (prompt_tokens, completion_tokens, total_tokens, cached_tokens, reasoning_tokens)
        )
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "reasoning_tokens": reasoning_tokens,
            "token_usage_available": token_usage_available,
        }

    @staticmethod
    def _should_retry_without_stream_usage(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(
            marker in message
            for marker in (
                "stream_options",
                "include_usage",
                "unknown parameter",
                "unexpected keyword argument",
                "extra inputs are not permitted",
                "unrecognized request argument",
            )
        )

    def _create_stream(self, client: OpenAI, messages: List[Dict[str, Any]], extra_body: Dict[str, Any]) -> Any:
        request_kwargs: Dict[str, Any] = {
            "model": self._config.api_config.get("model_name", "qwen3.6-35b-a3b"),
            "messages": messages,
            "extra_body": extra_body,
            "stream": True,
        }
        if self._stream_usage_supported is not False:
            request_kwargs["stream_options"] = {"include_usage": True}

        try:
            stream = client.chat.completions.create(**request_kwargs)
            if "stream_options" in request_kwargs:
                self._stream_usage_supported = True
            return stream
        except Exception as exc:
            if "stream_options" in request_kwargs and self._should_retry_without_stream_usage(exc):
                request_kwargs.pop("stream_options", None)
                self._stream_usage_supported = False
                print("当前接口不支持流式 usage，回退为不携带 stream_options 的流式请求")
                return client.chat.completions.create(**request_kwargs)
            raise

    def _create_completion(
        self,
        messages: List[Dict[str, Any]],
        should_exit_check: Optional[callable] = None,
        on_stream_chunk: Optional[Callable[[str], Any]] = None,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """执行模型调用并返回原始响应及计时指标"""
        if should_exit_check and should_exit_check():
            print("检测到退出标记，取消 API 调用")
            return None, {
                "model_latency_ms": 0.0,
                "first_chunk_ms": 0.0,
                **self._extract_usage_metrics(None),
            }

        client = self._get_client()
        extra_body = self._build_extra_body()

        start_time = time.perf_counter()
        if on_stream_chunk:
            stream = self._create_stream(client, messages, extra_body)
            raw_parts: List[str] = []
            first_chunk_ms = 0.0
            latest_usage = None

            try:
                for chunk in stream:
                    chunk_usage = getattr(chunk, "usage", None)
                    if chunk_usage is not None:
                        latest_usage = chunk_usage
                    if should_exit_check and should_exit_check():
                        print("检测到退出标记，取消流式 API 调用")
                        return None, {
                            "model_latency_ms": (time.perf_counter() - start_time) * 1000.0,
                            "first_chunk_ms": first_chunk_ms,
                            **self._extract_usage_metrics(latest_usage),
                        }

                    text = self._extract_text_from_stream_chunk(chunk)
                    if not text:
                        continue

                    raw_parts.append(text)
                    if first_chunk_ms == 0.0:
                        first_chunk_ms = (time.perf_counter() - start_time) * 1000.0

                    try:
                        on_stream_chunk(text)
                    except Exception as exc:
                        print(f"流式输出回调出错: {exc}")
            finally:
                close_method = getattr(stream, "close", None)
                if callable(close_method):
                    close_method()

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return "".join(raw_parts), {
                "model_latency_ms": latency_ms,
                "first_chunk_ms": first_chunk_ms,
                **self._extract_usage_metrics(latest_usage),
            }

        completion = client.chat.completions.create(
            model=self._config.api_config.get("model_name", "qwen3.6-35b-a3b"),
            messages=messages,
            extra_body=extra_body,
        )
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return completion.choices[0].message.content, {
            "model_latency_ms": latency_ms,
            "first_chunk_ms": latency_ms,
            **self._extract_usage_metrics(getattr(completion, "usage", None)),
        }

    def _extract_text_from_stream_chunk(self, chunk: Any) -> str:
        """从流式响应块中提取文本内容。"""
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return ""

        delta = getattr(choices[0], "delta", None)
        if delta is None:
            return ""

        content = getattr(delta, "content", None)
        return self._coerce_stream_content_to_text(content)

    def _coerce_stream_content_to_text(self, content: Any) -> str:
        """兼容不同 SDK 结构，将流式内容归一为字符串。"""
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue

                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                    continue

                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts)

        return str(content)

    def _parse_and_store_response(
        self,
        raw_content: str,
        action_feedback: str = "",
        log_raw_content: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """解析模型响应并写入结构化 assistant 记忆"""
        if log_raw_content:
            print(f"AI 原始返回内容: {raw_content}")
        parsed = self._parser.parse(raw_content)
        self._last_parse_error = self._parser.get_last_error()
        self._last_parse_error_envelope = self._parser.get_last_error_envelope()
        self._memory.add_assistant_message(
            raw_content,
            action_feedback=action_feedback,
            parsed_response=parsed
        )
        return parsed
    
    def analyze_screen(
        self,
        image_paths: Union[str, List[str]],
        user_content: str,
        screen_info: Optional[List[Dict[str, Any]]] = None,
        should_exit_check: Optional[callable] = None,
        on_stream_chunk: Optional[Callable[[str], Any]] = None,
        history_user_content: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        分析屏幕截图
        
        Args:
            image_paths: 截图路径（单个路径或路径列表）
            user_content: 用户输入内容
            screen_info: 屏幕信息列表
            should_exit_check: 退出检查函数
        
        Returns:
            解析后的AI响应字典
        """
        if isinstance(image_paths, str):
            image_paths = [image_paths]
        self._last_parse_error = ""
        self._last_parse_error_envelope = None
        
        for image_path in image_paths:
            if not os.path.exists(image_path):
                print(f"错误：图片文件不存在 - {os.path.abspath(image_path)}")
                return None
        
        api_key = self._config.api_config.get("api_key", "")
        if not api_key:
            print("提示：配置文件中未设置API Key，跳过模型分析")
            return None
        
        if should_exit_check and should_exit_check():
            print("检测到退出标志，跳过API调用")
            return None
        
        print("正在初始化OpenAI客户端并调用多模态模型分析图片...")
        
        if should_exit_check and should_exit_check():
            print("检测到退出标志，取消API调用")
            self._client = None
            return None
        
        system_content = self._load_prompt()
        
        print(f"模型是{self._config.api_config.get('model_name', 'unknown')}")
        
        screen_prompt = self._build_screen_prompt(screen_info) if screen_info else ""
        full_content = f"{screen_prompt}\n{user_content}" if screen_prompt else user_content
        history_content = self._build_history_user_content(
            history_user_content if history_user_content is not None else user_content
        )
        
        self._memory.add_user_message(image_paths, full_content, history_text=history_content)
        
        messages = self._memory.get_messages(system_content, latest_user_full=True)
        
        print(f"当前记忆消息数: {len(messages)} 条")
        summary = self._memory.get_memory_summary()
        print(f"记忆摘要: {summary}")
        
        try:
            raw_content, _ = self._create_completion(
                messages,
                should_exit_check=should_exit_check,
                on_stream_chunk=on_stream_chunk,
            )

            if raw_content is None:
                self._client = None
                return None

            parsed = self._parse_and_store_response(
                raw_content,
                log_raw_content=on_stream_chunk is None,
            )
            self._client = None
            
            if parsed:
                print("手动解析成功！")
                return parsed
            else:
                print("手动解析失败，无法处理 AI 返回的内容")
                return None
        
        except Exception as e:
            print(f"API调用出错: {e}")
            self._client = None
            return None
    
    def _build_screen_prompt(self, screen_info: List[Dict[str, Any]]) -> str:
        """构建屏幕信息提示"""
        return self._prompt_builder.build_screen_prompt(screen_info)
    
    def get_next_action(
        self,
        image_paths: Union[str, List[str]],
        user_content: str,
        previous_context: str = "",
        should_exit_check: Optional[callable] = None,
        action_feedback: str = "",
        screen_info: Optional[List[Dict[str, Any]]] = None,
        memory_content: str = "",
        on_stream_chunk: Optional[Callable[[str], Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        获取下一步 agent 响应
        
        Args:
            image_paths: 截图路径（单个路径或路径列表）
            user_content: 用户任务内容
            previous_context: 之前的上下文（已废弃，由记忆系统管理）
            should_exit_check: 退出检查函数
            action_feedback: 上一次操作的反馈
            screen_info: 屏幕信息列表
            memory_content: 重要信息记忆内容
        
        Returns:
            下一步 agent 响应
        """
        if action_feedback:
            self._memory.add_feedback_only(action_feedback)

        history_user_content = self._build_history_user_content(user_content)
        if memory_content:
            user_content = (
                f"{user_content}\n\n"
                f"[Important Information Memory (no need to remember what is already here)]\n{memory_content}"
            )
        
        return self.analyze_screen(
            image_paths,
            user_content,
            screen_info,
            should_exit_check,
            on_stream_chunk=on_stream_chunk,
            history_user_content=history_user_content,
        )

    def get_next_action_from_capture(
        self,
        captures: List[Any],
        user_content: str,
        should_exit_check: Optional[callable] = None,
        action_feedback: str = "",
        screen_info: Optional[List[Dict[str, Any]]] = None,
        memory_content: str = "",
        page_context: Optional[Dict[str, Any]] = None,
        page_extraction_notice: str = "",
        document_context: Optional[Dict[str, Any]] = None,
        document_extraction_notice: str = "",
        context_warning_prompt: str = "",
        replan_feedback: str = "",
        process_report_mode: str = "auto",
        process_report_request_prompt: str = "",
        held_modifier_prompt: str = "",
        frontmost_app_prompt: str = "",
        background_jobs_prompt: str = "",
        pending_reports_prompt: str = "",
        on_stream_chunk: Optional[Callable[[str], Any]] = None,
        respond_language_override: str = "",
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """基于内存中的截图 bundle 获取下一步 agent 响应，并返回性能指标"""
        self._last_parse_error = ""
        self._last_parse_error_envelope = None
        api_key = self._config.api_config.get("api_key", "")
        if not api_key:
            print("提示：配置文件中未设置 API Key，跳过模型分析")
            return None, {
                "encode_ms": 0.0,
                "request_prepare_ms": 0.0,
                "model_latency_ms": 0.0,
                "first_chunk_ms": 0.0,
            }

        if should_exit_check and should_exit_check():
            print("检测到退出标记，跳过 API 调用")
            return None, {
                "encode_ms": 0.0,
                "request_prepare_ms": 0.0,
                "model_latency_ms": 0.0,
                "first_chunk_ms": 0.0,
            }

        if action_feedback:
            self._memory.add_feedback_only(action_feedback)

        runtime_context = RuntimePromptContext(
            screen_info=screen_info,
            memory_content=memory_content,
            page_context=page_context,
            page_extraction_notice=page_extraction_notice,
            document_context=document_context,
            document_extraction_notice=document_extraction_notice,
            context_warning_prompt=context_warning_prompt,
            replan_feedback=replan_feedback,
            process_report_mode=process_report_mode,
            process_report_request_prompt=process_report_request_prompt,
            held_modifier_prompt=held_modifier_prompt,
            frontmost_app_prompt=frontmost_app_prompt,
            background_jobs_prompt=background_jobs_prompt,
            pending_reports_prompt=pending_reports_prompt,
        )
        full_content = self._build_full_user_content(
            user_content=user_content,
            runtime_context=runtime_context,
            respond_language_override=respond_language_override,
        )
        history_content = self._build_history_user_content(user_content)

        prepare_start = time.perf_counter()
        encode_start = time.perf_counter()
        self._memory.add_user_capture(captures, full_content, history_text=history_content)
        encode_ms = (time.perf_counter() - encode_start) * 1000.0

        system_content = self._load_prompt()
        messages = self._memory.get_messages(system_content, latest_user_full=True)
        request_prepare_ms = (time.perf_counter() - prepare_start) * 1000.0

        self._write_context_debug_log(full_content, messages)

        raw_content, completion_metrics = self._create_completion(
            messages,
            should_exit_check=should_exit_check,
            on_stream_chunk=on_stream_chunk,
        )
        if raw_content is None:
            return None, {
                "encode_ms": encode_ms,
                "request_prepare_ms": request_prepare_ms,
                **completion_metrics,
            }

        parsed = self._parse_and_store_response(
            raw_content,
            log_raw_content=on_stream_chunk is None,
        )
        return parsed, {
            "encode_ms": encode_ms,
            "request_prepare_ms": request_prepare_ms,
            **completion_metrics,
        }
    
    @classmethod
    def get_instance(cls, config: Optional[Config] = None) -> "AIClient":
        """获取客户端单例"""
        return cls(config)
