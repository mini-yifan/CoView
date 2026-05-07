import pytest

from baodou_ai.agent.protocol import get_agent_response_branch, normalize_agent_response, is_tool_branch


def test_normalize_agent_response_accepts_tool_call_branch():
    response = normalize_agent_response({
        "thinking": "需要点击按钮。",
        "report": "我先点击这个按钮。",
        "click": {
            "screen_index": "1",
            "position": [100, 200],
        },
    })

    assert response["thinking"] == "需要点击按钮。"
    assert response["report"] == "我先点击这个按钮。"
    assert response["click"]["screen_index"] == 1
    assert response["click"]["position"] == [100.0, 200.0]
    assert get_agent_response_branch(response) == "click"


def test_normalize_agent_response_accepts_scroll_tool_with_scroll_level():
    response = normalize_agent_response({
        "thinking": "当前需要更大幅度向下滚动。",
        "scroll_down": {
            "screen_index": "1",
            "position": [100, 200],
            "scroll_level": "6",
        },
    })

    assert response == {
        "thinking": "当前需要更大幅度向下滚动。",
        "scroll_down": {
            "screen_index": 1,
            "position": [100.0, 200.0],
            "scroll_level": 6,
        },
    }


def test_normalize_agent_response_accepts_open_in_finder_tool():
    response = normalize_agent_response({
        "thinking": "桌面对象较多，先在访达中打开桌面目录。",
        "open_in_finder": {},
    })

    assert response == {
        "thinking": "桌面对象较多，先在访达中打开桌面目录。",
        "open_in_finder": {},
    }


def test_normalize_agent_response_accepts_open_in_finder_with_path():
    response = normalize_agent_response({
        "thinking": "需要在访达中打开指定文件夹。",
        "open_in_finder": {
            "path": "/Users/test/Documents",
        },
    })

    assert response["open_in_finder"]["path"] == "/Users/test/Documents"


def test_normalize_agent_response_rejects_open_in_finder_blacklisted_path():
    with pytest.raises(ValueError, match="系统敏感路径"):
        normalize_agent_response({
            "thinking": "尝试打开系统目录。",
            "open_in_finder": {
                "path": "/etc",
            },
        })


def test_normalize_agent_response_accepts_read_current_page_tool():
    response = normalize_agent_response({
        "thinking": "我先快速读取当前网页正文。",
        "read_current_page": {},
    })

    assert response == {
        "thinking": "我先快速读取当前网页正文。",
        "read_current_page": {"mode": "extract"},
    }


def test_normalize_agent_response_accepts_read_current_document_tool():
    response = normalize_agent_response({
        "thinking": "我先快速读取当前文档正文。",
        "read_current_document": {},
    })

    assert response == {
        "thinking": "我先快速读取当前文档正文。",
        "read_current_document": {
            "mode": "extract",
            "follow_view": False,
        },
    }


def test_normalize_agent_response_accepts_read_current_document_tool_with_position():
    response = normalize_agent_response({
        "thinking": "我先点击正文区域再读取当前文档。",
        "read_current_document": {
            "screen_index": 0,
            "position": [321, 123],
        },
    })

    assert response == {
        "thinking": "我先点击正文区域再读取当前文档。",
        "read_current_document": {
            "mode": "extract",
            "follow_view": False,
            "screen_index": 0,
            "position": [321.0, 123.0],
        },
    }


def test_normalize_agent_response_accepts_read_current_document_chunk_mode():
    response = normalize_agent_response({
        "thinking": "我先读取当前文档的第 2 块。",
        "read_current_document": {
            "mode": "chunk",
            "chunk_index": 1,
        },
    })

    assert response == {
        "thinking": "我先读取当前文档的第 2 块。",
        "read_current_document": {
            "mode": "chunk",
            "follow_view": False,
            "chunk_index": 1,
        },
    }


def test_normalize_agent_response_accepts_read_current_document_next_mode():
    response = normalize_agent_response({
        "thinking": "我继续读取下一块。",
        "read_current_document": {
            "mode": "next",
        },
    })

    assert response == {
        "thinking": "我继续读取下一块。",
        "read_current_document": {
            "mode": "next",
            "follow_view": False,
        },
    }


def test_normalize_agent_response_accepts_read_current_document_search_mode():
    response = normalize_agent_response({
        "thinking": "我先搜索退款和违约金相关内容。",
        "read_current_document": {
            "mode": "search",
            "query": "退款 违约金",
        },
    })

    assert response == {
        "thinking": "我先搜索退款和违约金相关内容。",
        "read_current_document": {
            "mode": "search",
            "follow_view": False,
            "query": "退款 违约金",
            "top_k": 3,
        },
    }


def test_normalize_agent_response_accepts_read_current_document_with_follow_view_disabled():
    response = normalize_agent_response({
        "thinking": "我继续读取下一块，但不要移动文档视图。",
        "read_current_document": {
            "mode": "next",
            "follow_view": False,
        },
    })

    assert response == {
        "thinking": "我继续读取下一块，但不要移动文档视图。",
        "read_current_document": {
            "mode": "next",
            "follow_view": False,
        },
    }


def test_normalize_agent_response_rejects_read_current_document_chunk_without_chunk_index():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "我想读取某一块。",
            "read_current_document": {
                "mode": "chunk",
            },
        })


def test_normalize_agent_response_rejects_read_current_document_search_without_query():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "我想搜索关键词。",
            "read_current_document": {
                "mode": "search",
            },
        })


def test_normalize_agent_response_rejects_read_current_document_next_with_position():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "我继续读取下一块。",
            "read_current_document": {
                "mode": "next",
                "screen_index": 0,
                "position": [100, 200],
            },
        })


def test_normalize_agent_response_rejects_read_current_document_search_with_position():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "我想搜索关键词。",
            "read_current_document": {
                "mode": "search",
                "query": "hello",
                "screen_index": 0,
                "position": [100, 200],
            },
        })


def test_normalize_agent_response_rejects_read_current_document_with_invalid_follow_view():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "我继续读取下一块。",
            "read_current_document": {
                "mode": "next",
                "follow_view": "maybe",
            },
        })


def test_normalize_agent_response_rejects_scroll_level_out_of_range():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "我先小幅向下滚动。",
            "scroll_down": {
                "screen_index": 0,
                "position": [100, 200],
                "scroll_level": 11,
            },
        })


def test_normalize_agent_response_accepts_scroll_level_upper_bound():
    response = normalize_agent_response({
        "thinking": "我要快速向下滚动到页面更靠后的位置。",
        "scroll_down": {
            "screen_index": 0,
            "position": [100, 200],
            "scroll_level": 10,
        },
    })

    assert response["scroll_down"]["scroll_level"] == 10


def test_normalize_agent_response_rejects_scroll_multiplier_legacy_param():
    with pytest.raises(ValueError, match="scroll_level 参数，不再接受 multiplier"):
        normalize_agent_response({
            "thinking": "我要快速向下滚动到页面更靠后的位置。",
            "scroll_down": {
                "screen_index": 0,
                "position": [100, 200],
                "multiplier": 2,
            },
        })


def test_normalize_agent_response_accepts_hold_modifier_keys_tool():
    response = normalize_agent_response({
        "thinking": "需要多选文件，先保持 command 键。",
        "hold_modifier_keys": {
            "keys": ["command"],
        },
    })

    assert response == {
        "thinking": "需要多选文件，先保持 command 键。",
        "hold_modifier_keys": {
            "keys": ["command"],
        },
    }


def test_normalize_agent_response_accepts_release_modifier_keys_tool():
    response = normalize_agent_response({
        "thinking": "不再需要 command 键，先释放。",
        "release_modifier_keys": {},
    })

    assert response == {
        "thinking": "不再需要 command 键，先释放。",
        "release_modifier_keys": {},
    }


def test_normalize_agent_response_accepts_tool_call_with_remember():
    response = normalize_agent_response({
        "thinking": "这条信息后续还会用到，先记住再点击。",
        "report": "我先把任务记住。",
        "remember": {
            "content": "需要记住的重要信息",
        },
        "click": {
            "screen_index": 0,
            "position": [100, 200],
        },
    })

    assert response == {
        "thinking": "这条信息后续还会用到，先记住再点击。",
        "report": "我先把任务记住。",
        "remember": {
            "content": "需要记住的重要信息",
        },
        "click": {
            "screen_index": 0,
            "position": [100.0, 200.0],
        },
    }


def test_normalize_agent_response_ignores_empty_top_level_report_for_tool_branch():
    response = normalize_agent_response({
        "thinking": "当前不需要额外过程汇报，直接点击。",
        "report": "   ",
        "click": {
            "screen_index": 0,
            "position": [100, 200],
        },
    })

    assert response == {
        "thinking": "当前不需要额外过程汇报，直接点击。",
        "click": {
            "screen_index": 0,
            "position": [100.0, 200.0],
        },
    }


def test_normalize_agent_response_accepts_page_loading_with_remember():
    response = normalize_agent_response({
        "thinking": "当前只需要等待页面或界面稳定。",
        "report": "我正在等待页面稳定。",
        "remember": {
            "content": "页面提示账号未登录",
        },
        "page_loading": {},
    })

    assert response == {
        "thinking": "当前只需要等待页面或界面稳定。",
        "report": "我正在等待页面稳定。",
        "remember": {
            "content": "页面提示账号未登录",
        },
        "page_loading": {
            "mode": "short_wait",
        },
    }


def test_normalize_agent_response_accepts_page_loading_long_wait():
    response = normalize_agent_response({
        "thinking": "安装还在继续，先长等待。",
        "page_loading": {
            "mode": "long_wait",
            "wait_seconds": 5,
        },
    })

    assert response == {
        "thinking": "安装还在继续，先长等待。",
        "page_loading": {
            "mode": "long_wait",
            "wait_seconds": 5,
        },
    }


def test_normalize_agent_response_defaults_page_loading_to_short_wait():
    response = normalize_agent_response({
        "thinking": "当前只需要等待页面稳定。",
        "page_loading": {},
    })

    assert response["page_loading"] == {
        "mode": "short_wait",
    }


def test_normalize_agent_response_defaults_long_wait_seconds_to_three():
    response = normalize_agent_response({
        "thinking": "安装还在继续，先长等待。",
        "page_loading": {
            "mode": "long_wait",
        },
    })

    assert response["page_loading"] == {
        "mode": "long_wait",
        "wait_seconds": 3,
    }


def test_normalize_agent_response_rejects_invalid_page_loading_wait_seconds():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "测试",
            "page_loading": {
                "mode": "long_wait",
                "wait_seconds": 100,
            },
        })


def test_normalize_agent_response_accepts_respond_with_remember():
    response = normalize_agent_response({
        "thinking": "现在已经可以结束并向用户汇报结果。",
        "remember": {
            "content": "最终下载地址: https://example.com",
        },
        "respond": {
            "outcome": "completed",
            "report": "我已经完成任务，并把结果整理好了。",
        },
    })

    assert response == {
        "thinking": "现在已经可以结束并向用户汇报结果。",
        "remember": {
            "content": "最终下载地址: https://example.com",
        },
        "respond": {
            "outcome": "completed",
            "report": "我已经完成任务，并把结果整理好了。",
        },
    }


def test_normalize_agent_response_rejects_missing_thinking():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "click": {
                "screen_index": 0,
                "position": [100, 200],
            },
        })


def test_normalize_agent_response_rejects_multiple_branch_keys():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "测试",
            "click": {
                "screen_index": 0,
                "position": [100, 200],
            },
            "page_loading": {},
        })


def test_normalize_agent_response_rejects_status_protocol():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "测试",
            "status": "tool_call",
            "tool": {
                "name": "click",
                "args": {
                    "screen_index": 0,
                    "position": [100, 200],
                },
            },
        })


def test_normalize_agent_response_rejects_legacy_action_protocol():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "测试",
            "whether_completed": "False",
            "screen_index": 0,
            "coordinates": [321, 123],
            "action": "click",
            "type_information": "",
        })


def test_normalize_agent_response_rejects_missing_respond_report():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "测试",
            "respond": {
                "outcome": "completed",
            },
        })


def test_normalize_agent_response_rejects_empty_respond_report():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "测试",
            "respond": {
                "outcome": "completed",
                "report": "   ",
            },
        })


def test_normalize_agent_response_rejects_string_remember():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "测试",
            "click": {
                "screen_index": 0,
                "position": [100, 200],
            },
            "remember": "任务内容",
        })


def test_normalize_agent_response_rejects_only_remember_without_main_branch():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "测试",
            "remember": {
                "content": "任务内容",
            },
        })


def test_normalize_agent_response_ignores_top_level_report_with_respond():
    response = normalize_agent_response({
        "thinking": "测试",
        "report": "过程汇报",
        "respond": {
            "outcome": "completed",
            "report": "最终结果",
        },
    })

    assert response == {
        "thinking": "测试",
        "respond": {
            "outcome": "completed",
            "report": "最终结果",
        },
    }


def test_normalize_agent_response_ignores_empty_top_level_report_with_respond():
    response = normalize_agent_response({
        "thinking": "测试",
        "report": "",
        "respond": {
            "outcome": "completed",
            "report": "最终结果",
        },
    })

    assert response == {
        "thinking": "测试",
        "respond": {
            "outcome": "completed",
            "report": "最终结果",
        },
    }


def test_normalize_agent_response_rejects_unknown_tool():
    with pytest.raises(ValueError):
        normalize_agent_response({
            "thinking": "测试",
            "unknown_tool": {},
        })
