"""
响应解析器测试
"""

from baodou_ai.ai.parser import ResponseParser


class TestResponseParser:
    """响应解析器测试"""

    def setup_method(self):
        self.parser = ResponseParser()

    def test_parse_valid_tool_call_json(self):
        json_str = (
            '{"thinking": "测试", "report": "我先点击。", '
            '"click": {"screen_index": 0, "position": [100, 200]}}'
        )
        result = self.parser.parse(json_str)

        assert result is not None
        assert result["thinking"] == "测试"
        assert result["report"] == "我先点击。"
        assert result["click"]["screen_index"] == 0
        assert result["click"]["position"] == [100.0, 200.0]

    def test_parse_json_with_code_block(self):
        json_str = (
            '```json\n{"thinking": "现在已经可以结束并向用户汇报结果。", '
            '"respond": {"outcome": "completed", "report": "任务完成"}}\n```'
        )
        result = self.parser.parse(json_str)

        assert result is not None
        assert result["thinking"] == "现在已经可以结束并向用户汇报结果。"
        assert result["respond"]["outcome"] == "completed"
        assert result["respond"]["report"] == "任务完成"

    def test_parse_respond_ignores_top_level_report(self):
        json_str = (
            '{"thinking": "现在已经可以结束并向用户汇报结果。", '
            '"report": "过程汇报", '
            '"respond": {"outcome": "completed", "report": "最终结果"}}'
        )
        result = self.parser.parse(json_str)

        assert result is not None
        assert result["thinking"] == "现在已经可以结束并向用户汇报结果。"
        assert "report" not in result
        assert result["respond"]["report"] == "最终结果"

    def test_parse_tool_call_with_remember_json(self):
        json_str = (
            '{"thinking": "这条信息后续还会用到，先记住再点击。", '
            '"report": "我先记住任务。", '
            '"remember": {"content": "任务内容"}, '
            '"click": {"screen_index": 0, "position": [100, 200]}}'
        )
        result = self.parser.parse(json_str)

        assert result is not None
        assert result["thinking"] == "这条信息后续还会用到，先记住再点击。"
        assert result["remember"]["content"] == "任务内容"
        assert result["report"] == "我先记住任务。"
        assert result["click"]["screen_index"] == 0
        assert result["click"]["position"] == [100.0, 200.0]

    def test_parse_page_loading_with_remember_json(self):
        json_str = (
            '{"thinking": "当前只需要等待页面或界面稳定。", '
            '"report": "我正在等待页面稳定。", '
            '"remember": {"content": "页面提示账号未登录"}, '
            '"page_loading": {}}'
        )
        result = self.parser.parse(json_str)

        assert result is not None
        assert result["thinking"] == "当前只需要等待页面或界面稳定。"
        assert result["page_loading"] == {"mode": "short_wait"}
        assert result["report"] == "我正在等待页面稳定。"
        assert result["remember"]["content"] == "页面提示账号未登录"

    def test_parse_page_loading_long_wait_json(self):
        json_str = (
            '{"thinking": "安装还在继续，先长等待。", '
            '"page_loading": {"mode": "long_wait", "wait_seconds": 4}}'
        )
        result = self.parser.parse(json_str)

        assert result is not None
        assert result["thinking"] == "安装还在继续，先长等待。"
        assert result["page_loading"] == {"mode": "long_wait", "wait_seconds": 4}

    def test_parse_key_value_lines_for_tool_call(self):
        content = "\n".join([
            "thinking=需要先点击搜索框",
            "report=我先点击搜索框。",
            'click={"screen_index":0,"position":[321,123]}',
        ])

        result = self.parser.parse(content)

        assert result is not None
        assert result["thinking"] == "需要先点击搜索框"
        assert result["report"] == "我先点击搜索框。"
        assert result["click"]["screen_index"] == 0
        assert result["click"]["position"] == [321.0, 123.0]

    def test_parse_key_value_lines_for_remember(self):
        content = "\n".join([
            "thinking=这条信息后续还会用到，先记住。",
            'page_loading={}',
            'remember={"content":"任务内容"}',
        ])

        result = self.parser.parse(content)

        assert result is not None
        assert result["thinking"] == "这条信息后续还会用到，先记住。"
        assert result["remember"]["content"] == "任务内容"
        assert result["page_loading"] == {"mode": "short_wait"}

    def test_parse_key_value_lines_for_page_loading_long_wait(self):
        content = "\n".join([
            "thinking=安装还在继续，先长等待。",
            'page_loading={"mode":"long_wait","wait_seconds":5}',
        ])

        result = self.parser.parse(content)

        assert result is not None
        assert result["thinking"] == "安装还在继续，先长等待。"
        assert result["page_loading"] == {"mode": "long_wait", "wait_seconds": 5}

    def test_repair_preserves_nested_tool_object_closing_braces(self):
        content = (
            '{\n'
            '"thinking": "系统设置已打开，当前显示的是通用页面。我需要在左侧导航栏中找到鼠标设置选项来开启自然滚动功能。'
            '从左侧菜单可以看到有多个选项，但当前没有看到"鼠标"选项。可能需要向下滚动左侧菜单才能找到鼠标设置。",\n'
            '"scroll_up": {\n'
            '"screen_index":0,\n'
            '"position":[120, 500],\n'
            '"scroll_level": 3}\n'
            '}'
        )

        result = self.parser.parse(content)

        assert result is not None
        assert result["thinking"].endswith("可能需要向下滚动左侧菜单才能找到鼠标设置。")
        assert result["scroll_up"]["screen_index"] == 0
        assert result["scroll_up"]["position"] == [120.0, 500.0]
        assert result["scroll_up"]["scroll_level"] == 3

    def test_repair_adds_missing_outer_closing_brace(self):
        content = (
            '{\n'
            '"thinking": "需要继续滚动",\n'
            '"scroll_up": {\n'
            '"screen_index":0,\n'
            '"position":[120, 500],\n'
            '"scroll_level": 3}\n'
        )

        result = self.parser.parse(content)

        assert result is not None
        assert result["thinking"] == "需要继续滚动"
        assert result["scroll_up"]["scroll_level"] == 3

    def test_parse_rejects_only_remember_without_main_branch(self):
        result = self.parser.parse(
            '{"thinking":"测试","remember":{"content":"任务内容"}}'
        )

        assert result is None

    def test_parse_rejects_old_status_protocol(self):
        result = self.parser.parse(
            '{"thinking":"测试","status":"tool_call","tool":{"name":"click","args":{"screen_index":0,"position":[100,200]}}}'
        )

        assert result is None

    def test_parse_rejects_old_legacy_protocol(self):
        result = self.parser.parse(
            '{"thinking":"测试","completed":"False","element_info":"按钮","coordinates":[100,200],"action":"click","type_information":""}'
        )

        assert result is None

    def test_parse_records_validation_error_for_invalid_manage_files_batch(self):
        result = self.parser.parse(
            '{"thinking":"分批删除这些文件","manage_files":{"mode":"delete","paths":['
            + ",".join(f'"file_{idx}.txt"' for idx in range(21))
            + "]}}"
        )

        assert result is None
        assert "单次最多删除 20 个条目" in self.parser.get_last_error()

    def test_parse_clears_last_error_after_success(self):
        self.parser.parse(
            '{"thinking":"分批删除这些文件","manage_files":{"mode":"delete","paths":['
            + ",".join(f'"file_{idx}.txt"' for idx in range(21))
            + "]}}"
        )

        result = self.parser.parse(
            '{"thinking":"先点击","click":{"screen_index":0,"position":[100,200]}}'
        )

        assert result is not None
        assert self.parser.get_last_error() == ""
        assert self.parser.get_last_error_envelope() is None

    def test_parse_records_error_envelope_for_invalid_json(self):
        result = self.parser.parse('{"thinking": "missing brace"')

        assert result is None
        envelope = self.parser.get_last_error_envelope()
        assert envelope is not None
        assert envelope["source"] == "parser"
        assert envelope["kind"] == "protocol_parse_failed"
        assert envelope["code"] == "PARSER_FAILED"
        assert envelope["retryable"] is True

    def test_validate_valid_response(self):
        response = {
            "thinking": "测试",
            "click": {"screen_index": 0, "position": [100, 200]},
        }

        assert self.parser.validate(response) is True

    def test_validate_invalid_tool(self):
        response = {
            "thinking": "测试",
            "invalid_action": {"screen_index": 0, "position": [100, 200]},
        }

        assert self.parser.validate(response) is False

    def test_validate_requires_thinking(self):
        response = {
            "click": {"screen_index": 0, "position": [100, 200]},
        }

        assert self.parser.validate(response) is False

    def test_validate_accepts_hold_modifier_keys(self):
        response = {
            "thinking": "需要多选文件，先保持 command 键。",
            "hold_modifier_keys": {"keys": ["command"]},
        }

        assert self.parser.validate(response) is True

    def test_validate_rejects_hold_modifier_keys_with_non_modifier(self):
        response = {
            "thinking": "测试",
            "hold_modifier_keys": {"keys": ["a"]},
        }

        assert self.parser.validate(response) is False

    def test_validate_accepts_release_modifier_keys_without_keys(self):
        response = {
            "thinking": "不再需要 command 键了，先释放。",
            "release_modifier_keys": {},
        }

        assert self.parser.validate(response) is True

    def test_extract_agent_response_returns_new_protocol(self):
        response = self.parser.extract_agent_response({
            "thinking": "测试",
            "click": {
                "screen_index": 0,
                "position": [10, 20],
            },
        })

        assert "click" in response
        assert response["click"]["screen_index"] == 0
        assert response["click"]["position"] == [10.0, 20.0]
