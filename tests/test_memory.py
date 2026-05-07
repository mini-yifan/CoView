import json

from baodou_ai.ai.memory import MemoryManager
from baodou_ai.core.screenshot import ScreenCaptureBundle


def test_memory_reuses_cached_capture_data_urls():
    memory = MemoryManager({
        "memory_config": {
            "max_text_memory": 25,
            "max_image_memory": 3,
        }
    })

    first_capture = {
        "index": 0,
        "frame_hash": "same-frame",
        "data_url": "data:image/png;base64,AAA",
    }
    second_capture = {
        "index": 0,
        "frame_hash": "same-frame",
        "data_url": None,
    }

    memory.add_user_capture([first_capture], "first")
    memory.add_user_capture([second_capture], "second")

    messages = memory.get_last_n_messages(2)
    second_message = messages[-1]
    image_items = [item for item in second_message["content"] if item.get("type") == "image_url"]

    assert len(memory._image_cache) == 1
    assert len(image_items) == 1
    assert image_items[0]["image_url"]["url"] == "data:image/png;base64,AAA"


def test_memory_keeps_only_three_image_groups():
    memory = MemoryManager({
        "memory_config": {
            "max_text_memory": 25,
            "max_image_memory": 3,
        }
    })

    for idx in range(4):
        memory.add_user_capture([{
            "index": idx,
            "frame_hash": f"frame-{idx}",
            "data_url": f"data:image/png;base64,{idx}",
        }], f"group-{idx}")

    summary = memory.get_memory_summary()

    assert summary["image_group_count"] == 3


def test_memory_accepts_screen_capture_bundle_objects():
    memory = MemoryManager({
        "memory_config": {
            "max_text_memory": 25,
            "max_image_memory": 3,
        }
    })

    bundle = ScreenCaptureBundle(
        index=1,
        x=0,
        y=0,
        width=320,
        height=240,
        logical_width=320,
        logical_height=240,
        is_primary=False,
        png_bytes=b"png",
        data_url="data:image/png;base64,BBB",
        frame_hash="bundle-frame",
        path=None,
    )

    memory.add_user_capture([bundle], "bundle capture")

    messages = memory.get_last_n_messages(1)
    image_items = [item for item in messages[0]["content"] if item.get("type") == "image_url"]

    assert len(image_items) == 1
    assert image_items[0]["image_url"]["url"] == "data:image/png;base64,BBB"


def test_memory_projects_historical_user_messages_to_task_only_text():
    memory = MemoryManager()

    capture = {
        "index": 0,
        "frame_hash": "frame-1",
        "data_url": "data:image/png;base64,AAA",
    }
    history_text = "[Current Task]\nUser task: 打开微信"
    full_text = (
        "[Current Task]\nCurrent time: 2026-04-10 16:00\nUser task: 打开微信\n\n"
        "[Frontmost App]\nCurrent frontmost app: 访达。"
    )

    memory.add_user_capture([capture], full_text, history_text=history_text)

    projected_messages = memory.get_messages("system", latest_user_full=False)
    latest_full_messages = memory.get_messages("system", latest_user_full=True)

    projected_text = "".join(
        item["text"]
        for item in projected_messages[1]["content"]
        if item.get("type") == "text"
    )
    latest_full_text = "".join(
        item["text"]
        for item in latest_full_messages[1]["content"]
        if item.get("type") == "text"
    )

    assert history_text in projected_text
    assert "Current time: 2026-04-10 16:00" not in projected_text
    assert "Current frontmost app: 访达。" not in projected_text
    assert full_text in latest_full_text
    assert "Current frontmost app: 访达。" in latest_full_text


def test_assistant_memory_is_saved_as_normalized_json():
    memory = MemoryManager()

    memory.add_assistant_message(
        '{"thinking":"测试","click":{"screen_index":"1","position":[321,123]}}',
        parsed_response={
            "thinking": "测试",
            "click": {
                "screen_index": "1",
                "position": [321, 123],
            },
        },
    )

    messages = memory.get_last_n_messages(1)
    assistant_payload = json.loads(messages[0]["content"])

    assert "click" in assistant_payload
    assert assistant_payload["click"]["screen_index"] == 1
    assert assistant_payload["click"]["position"] == [321.0, 123.0]
    assert "thinking=" not in messages[0]["content"]


def test_assistant_memory_keeps_report_and_remember_in_history():
    memory = MemoryManager()

    memory.add_assistant_message(
        '{"thinking":"测试","report":"正在执行","remember":{"content":"关键内容"},"click":{"screen_index":"1","position":[321,123]}}',
        parsed_response={
            "thinking": "测试",
            "report": "正在执行",
            "remember": {
                "content": "关键内容",
            },
            "click": {
                "screen_index": "1",
                "position": [321, 123],
            },
        },
    )

    messages = memory.get_last_n_messages(1)
    assistant_payload = json.loads(messages[0]["content"])

    assert assistant_payload["thinking"] == "测试"
    assert "click" in assistant_payload
    assert assistant_payload["report"] == "正在执行"
    assert assistant_payload["remember"] == {"content": "关键内容"}


def test_assistant_memory_keeps_respond_report_in_history():
    memory = MemoryManager()

    memory.add_assistant_message(
        '{"thinking":"完成","respond":{"outcome":"completed","report":"任务完成"}}',
        parsed_response={
            "thinking": "完成",
            "respond": {
                "outcome": "completed",
                "report": "任务完成",
            },
        },
    )

    messages = memory.get_last_n_messages(1)
    assistant_payload = json.loads(messages[0]["content"])

    assert assistant_payload == {
        "thinking": "完成",
        "respond": {
            "outcome": "completed",
            "report": "任务完成",
        },
    }


def test_assistant_memory_skips_unparsed_non_json_output():
    memory = MemoryManager()

    memory.add_assistant_message("thinking=点击搜索框\ncompleted=False\naction=click")

    assert memory.get_last_n_messages(1) == []


def test_feedback_only_preserves_file_listing_lines():
    memory = MemoryManager()

    listing_lines = "\n".join(
        f"📄 /tmp/file_{idx}.docx"
        for idx in range(1, 13)
    )
    feedback = (
        "Executed manage_files tool, args: {'mode': 'search'}, result: \n"
        "Search directory: /tmp\n"
        "Query: .docx\n\n"
        f"{listing_lines}\n\n"
        "Found 12 results"
    )

    memory.add_feedback_only(feedback)

    messages = memory.get_last_n_messages(1)
    assert len(messages) == 1
    content_items = messages[0]["content"]
    text = "".join(item.get("text", "") for item in content_items if item.get("type") == "text")

    # 不应被压成一行或截断到只剩前几条
    assert "file_12.docx" in text
    assert "\n📄 /tmp/file_12.docx" in text


def test_feedback_only_preserves_document_content_blocks():
    memory = MemoryManager()

    doc_body = "\n".join(
        f"第 {idx} 行文档内容，包含较长的说明文字和链接 https://example.com/{idx}"
        for idx in range(1, 40)
    )
    feedback = (
        "Executed read_current_document tool, args: {'mode': 'next'}, result: 已读取当前文档第 2/5 块。"
        "\n\n--- Document Content (App: Microsoft Word, Chunk: 2/5, Mode: next) ---\n"
        f"{doc_body}\n"
        "--- End of Document Content ---"
    )

    memory.add_feedback_only(feedback)

    messages = memory.get_last_n_messages(1)
    assert len(messages) == 1
    content_items = messages[0]["content"]
    text = "".join(item.get("text", "") for item in content_items if item.get("type") == "text")

    assert "--- Document Content (App: Microsoft Word, Chunk: 2/5, Mode: next) ---" in text
    assert "第 39 行文档内容" in text
    assert "https://example.com/39" in text
