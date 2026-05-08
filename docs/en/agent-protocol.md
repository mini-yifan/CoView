# Agent Protocol

CoView expects the model to return one primary branch per turn. The runner validates the branch, executes exactly one main action, observes the next state, and continues.

## Branch Types

The top-level JSON object should contain one of:

- A tool branch such as `click`, `input_text`, `hotkey`, `open_in_browser`, or `read_current_document`.
- `page_loading`, when the page or app is still changing and the agent should wait before acting.
- `respond`, when the task is complete or the agent must report a final answer.

Optional fields such as `thinking`, `report`, and `remember` can be attached.

## Example Tool Branch

```json
{
  "thinking": "The search field is visible, so I can enter the query directly.",
  "report": "I am searching from the browser input field.",
  "input_text": {
    "screen_index": 0,
    "position": [520, 150],
    "text": "weather in Shanghai",
    "replace": true,
    "submit": true
  }
}
```

## Example Page Loading Branch

```json
{
  "thinking": "The browser is loading the result page.",
  "report": "I am waiting for the page to finish loading.",
  "page_loading": {
    "duration_ms": 1500
  }
}
```

## Example Respond Branch

```json
{
  "thinking": "The requested information is visible and summarized.",
  "respond": {
    "text": "The article says..."
  }
}
```

## Important Files

- `src/baodou_ai/agent/protocol.py`: branch recognition and normalization.
- `src/baodou_ai/agent/tool_registry.py`: tool definitions and argument normalization.
- `src/baodou_ai/agent/tool_executor.py`: dispatch from tool name to `AutomationController.tool_*`.
- `src/baodou_ai/ai/parser.py`: model response parsing.
- `src/baodou_ai/core/runner_turns.py`: branch execution and feedback.

