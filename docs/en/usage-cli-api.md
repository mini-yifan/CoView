# CLI & Python API

## GUI

Start the floating assistant:

```bash
coview
```

## CLI

```bash
coview-cli "Open the browser and search CoView" --api-key YOUR_API_KEY
coview-cli "Close the active window" --max-iterations 10
coview-cli "Read the current page and summarize it" --base-url https://api.example.com
```

Windows:

```powershell
coview-cli "Open Notepad and type Hello" --api-key YOUR_API_KEY
coview-cli "Close the active window" --max-iterations 10
coview-cli "Read the current page and summarize it" --base-url https://api.example.com
```

Common CLI options:

| Option | Purpose |
| --- | --- |
| `--api-key` / `-k` | API key |
| `--base-url` / `-u` | OpenAI-compatible API base URL |
| `--model-name` / `-m` | Model name |
| `--max-iterations` / `-i` | Maximum control-loop steps |
| `--version` / `-v` | Print version |

## Python API

```python
from baodou_ai import CoViewAI

ai = CoViewAI(
    api_key="YOUR_API_KEY",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model_name="qwen3.6-35b-a3b",
)

result = ai.execute(
    "Open the browser, search for today's AI news, and summarize the top results.",
    max_iterations=30,
)

print(result)
```

With progress callbacks:

```python
from baodou_ai import CoViewAI

ai = CoViewAI(api_key="YOUR_API_KEY")

def on_iteration(index, info):
    print(f"[step {index + 1}] {info.get('thinking', '')}")

result = ai.execute(
    "Open Calculator and compute 128 * 46.",
    on_iteration=on_iteration,
)
```

Convenience function:

```python
from baodou_ai import execute_task

result = execute_task(
    "Open the browser",
    api_key="YOUR_API_KEY",
    max_iterations=10,
)
```

