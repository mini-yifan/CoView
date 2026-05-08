# Agent 协议

同窗要求模型每一轮返回一个主分支。Runner 会校验该分支、执行一个主操作、观察下一帧状态，然后继续循环。

## 分支类型

顶层 JSON 对象应该包含以下之一：

- 工具分支，例如 `click`、`input_text`、`hotkey`、`open_in_browser`、`read_current_document`。
- `page_loading`：页面或应用仍在变化，需要等待再观察。
- `respond`：任务已经完成，或需要返回最终结果。

可以附加 `thinking`、`report`、`remember` 等字段。

## 工具分支示例

```json
{
  "thinking": "搜索框可见，可以直接输入查询内容。",
  "report": "我正在浏览器输入框里搜索。",
  "input_text": {
    "screen_index": 0,
    "position": [520, 150],
    "text": "上海天气",
    "replace": true,
    "submit": true
  }
}
```

## 页面加载分支示例

```json
{
  "thinking": "浏览器正在加载结果页。",
  "report": "我正在等待页面加载完成。",
  "page_loading": {
    "duration_ms": 1500
  }
}
```

## 最终回复分支示例

```json
{
  "thinking": "请求的信息已经可见并完成总结。",
  "respond": {
    "text": "这篇文章主要说..."
  }
}
```

## 关键文件

- `src/baodou_ai/agent/protocol.py`：分支识别与归一化。
- `src/baodou_ai/agent/tool_registry.py`：工具定义与参数归一化。
- `src/baodou_ai/agent/tool_executor.py`：从工具名分发到 `AutomationController.tool_*`。
- `src/baodou_ai/ai/parser.py`：模型响应解析。
- `src/baodou_ai/core/runner_turns.py`：分支执行与反馈。

