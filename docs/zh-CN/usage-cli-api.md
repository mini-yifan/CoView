# CLI 与 Python API

## GUI

启动悬浮助手：

```bash
coview
```

## CLI

macOS / Linux:

```bash
coview-cli "打开浏览器并搜索同窗" --api-key YOUR_API_KEY
coview-cli "关闭当前窗口" --max-iterations 10
coview-cli "读取当前页面并总结" --base-url https://api.example.com
```

Windows:

```powershell
coview-cli "打开记事本并输入 Hello" --api-key YOUR_API_KEY
coview-cli "关闭当前窗口" --max-iterations 10
coview-cli "读取当前页面并总结" --base-url https://api.example.com
```

常用参数：

| 参数 | 作用 |
| --- | --- |
| `--api-key` / `-k` | API Key |
| `--base-url` / `-u` | OpenAI-compatible API 地址 |
| `--model-name` / `-m` | 模型名称 |
| `--max-iterations` / `-i` | 最大执行步数 |
| `--version` / `-v` | 显示版本 |

## Python API

```python
from baodou_ai import CoViewAI

ai = CoViewAI(
    api_key="YOUR_API_KEY",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model_name="qwen3.6-35b-a3b",
)

result = ai.execute(
    "打开浏览器，搜索今天的 AI 新闻，并总结排名靠前的结果。",
    max_iterations=30,
)

print(result)
```

带进度回调：

```python
from baodou_ai import CoViewAI

ai = CoViewAI(api_key="YOUR_API_KEY")

def on_iteration(index, info):
    print(f"[第 {index + 1} 步] {info.get('thinking', '')}")

result = ai.execute(
    "打开计算器并计算 128 * 46。",
    on_iteration=on_iteration,
)
```

便捷函数：

```python
from baodou_ai import execute_task

result = execute_task(
    "打开浏览器",
    api_key="YOUR_API_KEY",
    max_iterations=10,
)
```

