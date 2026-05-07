"""
响应解析模块

解析AI模型返回的JSON响应。
"""

import json
import re
from typing import Any, Dict, Optional, List

from baodou_ai.agent.protocol import NON_BRANCH_KEYS, normalize_agent_response
from baodou_ai.core.error_envelope import (
    CODE_PARSER_FAILED,
    KIND_PROTOCOL_PARSE_FAILED,
    SOURCE_PARSER,
    from_exception,
    from_message,
)


class ResponseParser:
    """AI响应解析器"""

    def __init__(self) -> None:
        self._last_error = ""
        self._last_error_envelope: Optional[Dict[str, Any]] = None

    def get_last_error(self) -> str:
        """返回最近一次解析失败原因；成功时为空字符串。"""
        return self._last_error

    def get_last_error_envelope(self) -> Optional[Dict[str, Any]]:
        """返回最近一次解析失败的结构化错误。"""
        return dict(self._last_error_envelope or {}) if self._last_error_envelope else None

    def _clear_last_error(self) -> None:
        self._last_error = ""
        self._last_error_envelope = None

    def _set_last_error(self, message: Any) -> None:
        self._last_error = str(message or "").strip()

    def _set_last_error_envelope(self, envelope: Dict[str, Any]) -> None:
        self._last_error_envelope = dict(envelope or {})
        if self._last_error_envelope:
            message = str(self._last_error_envelope.get("user_message") or "")
            detail = str(self._last_error_envelope.get("dev_detail") or "")
            self._last_error = (detail or message).strip()

    def parse(self, content: str) -> Optional[Dict[str, Any]]:
        """
        解析AI输出的JSON字符串
        
        Args:
            content: AI返回的原始内容
        
        Returns:
            解析后的字典，解析失败返回None
        """
        self._clear_last_error()
        if not content:
            envelope = from_message(
                source=SOURCE_PARSER,
                kind=KIND_PROTOCOL_PARSE_FAILED,
                user_message="模型响应解析失败",
                dev_detail="模型未返回任何内容",
                code=CODE_PARSER_FAILED,
                retryable=True,
            )
            self._set_last_error_envelope(envelope.to_dict())
            return None
        
        try:
            content = self._preprocess(content)

            if content.startswith("{") and content.endswith("}"):
                parsed = normalize_agent_response(
                    self._normalize_parsed_response(json.loads(content))
                )
                self._clear_last_error()
                return parsed

            if content.startswith("{") and not content.endswith("}"):
                repaired_result = self._repair_and_parse(content)
                if repaired_result is not None:
                    return repaired_result

            key_value_result = self._parse_key_value_lines(content)
            if key_value_result is not None:
                return key_value_result
            
            json_pattern = r'\{\s*"(?:[^"\\]|\\.)*"\s*:\s*(?:"(?:[^"\\]|\\.)*"|\d+\.?\d*|true|false|null|\[.*?\]|\{.*?\})\s*(?:,\s*"(?:[^"\\]|\\.)*"\s*:\s*(?:"(?:[^"\\]|\\.)*"|\d+\.?\d*|true|false|null|\[.*?\]|\{.*?\})\s*)*\}'
            
            json_matches = re.findall(json_pattern, content, re.DOTALL)
            
            if json_matches:
                valid_json = max(json_matches, key=len)
                print(f"从AI输出中提取的JSON: {valid_json}")
                parsed = normalize_agent_response(self._normalize_parsed_response(json.loads(valid_json)))
                self._clear_last_error()
                return parsed
            
            return self._fallback_parse(content)
        
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")
            envelope = from_exception(
                e,
                source=SOURCE_PARSER,
                kind=KIND_PROTOCOL_PARSE_FAILED,
                user_message="模型响应解析失败",
                code=CODE_PARSER_FAILED,
                retryable=True,
            )
            self._set_last_error_envelope(envelope.to_dict())
            return self._repair_and_parse(content)

        except Exception as e:
            print(f"解析过程中发生错误: {e}")
            envelope = from_exception(
                e,
                source=SOURCE_PARSER,
                kind=KIND_PROTOCOL_PARSE_FAILED,
                user_message="模型响应解析失败",
                code=CODE_PARSER_FAILED,
                retryable=True,
            )
            self._set_last_error_envelope(envelope.to_dict())
            return None
    
    def _preprocess(self, content: str) -> str:
        """预处理内容"""
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()

    def _parse_key_value_lines(self, content: str) -> Optional[Dict[str, Any]]:
        """解析 `key=value` 或 `key: value` 的多行输出。"""
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return None

        parsed: Dict[str, Any] = {}
        matched_line_count = 0
        for line in lines:
            separator = "=" if "=" in line else ":" if ":" in line else None
            if separator is None:
                continue

            key, value = line.split(separator, 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue

            parsed[key] = self._coerce_scalar_value(value)
            matched_line_count += 1

        branch_keys = [k for k in parsed if k not in NON_BRANCH_KEYS]
        if matched_line_count < 2 and not branch_keys:
            return None

        normalized = normalize_agent_response(self._normalize_parsed_response(parsed))
        self._clear_last_error()
        return normalized

    def _coerce_scalar_value(self, value: str) -> Any:
        """将简单字符串值转换为更合适的类型。"""
        stripped = value.strip()
        if not stripped:
            return ""

        if stripped in ("True", "False", "difficult"):
            return stripped

        if (
            stripped.startswith("[") and stripped.endswith("]")
        ) or (
            stripped.startswith("{") and stripped.endswith("}")
        ):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return stripped

        if re.fullmatch(r"-?\d+", stripped):
            try:
                return int(stripped)
            except ValueError:
                return stripped

        return stripped

    def _normalize_parsed_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """保持解析结果的原始结构。"""
        return dict(response)
    
    def _fallback_parse(self, content: str) -> Optional[Dict[str, Any]]:
        """备用解析方法"""
        print("正则匹配JSON失败，尝试原始方法")
        
        first_brace = content.find("{")
        last_brace = content.rfind("}")
        
        if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
            valid_json = content[first_brace : last_brace + 1]
            valid_json = self._fix_json_control_chars(valid_json)
            valid_json = self._escape_quotes_in_values(valid_json)
            print(f"提取的有效JSON: {valid_json}")
            parsed = normalize_agent_response(self._normalize_parsed_response(json.loads(valid_json)))
            self._clear_last_error()
            return parsed

        content = self._fix_json_control_chars(content)
        content = self._escape_quotes_in_values(content)
        parsed = normalize_agent_response(self._normalize_parsed_response(json.loads(content)))
        self._clear_last_error()
        return parsed
    
    def _fix_json_control_chars(self, json_str: str) -> str:
        """
        修复 JSON 字符串中的控制字符和特殊字符
        
        处理字符串值中未转义的换行符、制表符等控制字符
        同时处理字符串内部的双引号等可能干扰解析的字符
        """
        result = []
        in_string = False
        escape_next = False
        i = 0
        
        while i < len(json_str):
            char = json_str[i]
            
            if escape_next:
                result.append(char)
                escape_next = False
                i += 1
                continue
            
            if char == '\\' and in_string:
                result.append(char)
                escape_next = True
                i += 1
                continue
            
            if char == '"':
                in_string = not in_string
                result.append(char)
                i += 1
                continue
            
            if in_string:
                if char == '\n':
                    result.append('\\n')
                elif char == '\r':
                    result.append('\\r')
                elif char == '\t':
                    result.append('\\t')
                elif ord(char) < 32:
                    result.append(f'\\u{ord(char):04x}')
                else:
                    result.append(char)
            else:
                result.append(char)
            
            i += 1
        
        return ''.join(result)
    
    def _escape_quotes_in_values(self, json_str: str) -> str:
        """
        转义 JSON 字符串值内部的未转义双引号
        
        这是更激进的修复方法，直接处理常见的 value 字段
        """
        import re
        
        json_str = self._escape_field_quotes(json_str, "thinking")
        json_str = self._escape_field_quotes(json_str, "report")
        json_str = self._escape_field_quotes(json_str, "message")
        json_str = self._escape_field_quotes(json_str, "summary")
        json_str = self._escape_field_quotes(json_str, "reason")
        json_str = self._escape_field_quotes(json_str, "element_info")
        json_str = self._escape_field_quotes(json_str, "type_information")
        json_str = self._escape_field_quotes(json_str, "content")
        
        return json_str
    
    def _escape_field_quotes(self, json_str: str, field_name: str) -> str:
        """转义指定字段值内部的未转义双引号"""
        import re
        
        pattern = rf'"{field_name}"\s*:\s*"(.*?)"(?=\s*,|\s*}}|\s*\n)'
        
        def replace_quotes(match):
            value = match.group(1)
            escaped_value = re.sub(r'(?<!\\)"', r'\\"', value)
            return f'"{field_name}": "{escaped_value}"'
        
        return re.sub(pattern, replace_quotes, json_str, flags=re.DOTALL)

    def _strip_duplicate_outer_braces(self, json_str: str) -> str:
        """只移除模型偶发输出的双层外壳 `{{...}}`，不改正常嵌套对象的 `}}` 结尾。"""
        stripped = json_str.strip()
        if not (stripped.startswith("{{") and stripped.endswith("}}")):
            return json_str

        candidate = stripped[1:-1].strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            return candidate
        return json_str

    def _balance_json_containers(self, json_str: str) -> str:
        """补齐缺失的 JSON 对象/数组闭合符，并忽略无法匹配的多余闭合符。"""
        result = []
        stack: List[str] = []
        in_string = False
        escape_next = False
        closing_for = {"{": "}", "[": "]"}
        opening_for = {"}": "{", "]": "["}

        for char in json_str:
            if escape_next:
                result.append(char)
                escape_next = False
                continue

            if in_string:
                result.append(char)
                if char == "\\":
                    escape_next = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
                result.append(char)
                continue

            if char in closing_for:
                stack.append(char)
                result.append(char)
                continue

            if char in opening_for:
                if stack and stack[-1] == opening_for[char]:
                    stack.pop()
                    result.append(char)
                continue

            result.append(char)

        while stack:
            result.append(closing_for[stack.pop()])

        return ''.join(result)
    
    def _repair_and_parse(self, content: str) -> Optional[Dict[str, Any]]:
        """修复并解析JSON"""
        try:
            cleaned_str = self._strip_duplicate_outer_braces(content)
            cleaned_str = self._fix_json_control_chars(cleaned_str)
            cleaned_str = self._escape_quotes_in_values(cleaned_str)
            cleaned_str = self._balance_json_containers(cleaned_str)
            print(f"清理后的JSON: {cleaned_str}")
            parsed = normalize_agent_response(self._normalize_parsed_response(json.loads(cleaned_str)))
            self._clear_last_error()
            return parsed
        except json.JSONDecodeError as e:
            print(f"二次解析失败: {e}")
            envelope = from_exception(
                e,
                source=SOURCE_PARSER,
                kind=KIND_PROTOCOL_PARSE_FAILED,
                user_message="模型响应解析失败",
                code=CODE_PARSER_FAILED,
                retryable=True,
            )
            self._set_last_error_envelope(envelope.to_dict())
            return None
        except Exception as e:
            print(f"协议归一化失败: {e}")
            envelope = from_exception(
                e,
                source=SOURCE_PARSER,
                kind=KIND_PROTOCOL_PARSE_FAILED,
                user_message="模型响应解析失败",
                code=CODE_PARSER_FAILED,
                retryable=True,
            )
            self._set_last_error_envelope(envelope.to_dict())
            return None
    
    def validate(self, response: Dict[str, Any]) -> bool:
        """
        验证响应格式
        
        Args:
            response: 解析后的响应字典
        
        Returns:
            是否有效
        """
        try:
            normalize_agent_response(response)
            return True
        except Exception as e:
            print(f"响应校验失败: {e}")
            return False
    
    def extract_agent_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """提取 agent 协议信息。"""
        return normalize_agent_response(response)
