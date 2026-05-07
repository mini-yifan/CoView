# 包豆电脑 API 使用文档

本文档说明如何在其他项目中使用包豆电脑的 API 接口。

## 快速开始

### 1. 安装

确保你已经安装了包豆电脑项目。

### 2. 导入 API

```python
from baodou_ai import BaodouAI, execute_task
```

## API 参考

### BaodouAI 类

主要的自动化控制器类。

#### 构造函数

```python
BaodouAI(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
    config: Optional[Config] = None,
)
```

**参数:**
- `api_key`: API 密钥（可选，配置文件中已设置可省略）
- `base_url`: API 基础地址（可选）
- `model_name`: 模型名称（可选）
- `config`: 配置对象（可选，不提供会自动加载默认配置）

#### execute() 方法

执行自动化任务。

```python
execute(
    task: str,
    max_iterations: Optional[int] = None,
    on_iteration: Optional[Callable[[int, dict], Any]] = None,
    on_model_stream: Optional[Callable[[int, str], Any]] = None,
    on_transparent_enter: Optional[Callable[[], Any]] = None,
    on_transparent_exit: Optional[Callable[[], Any]] = None,
) -> str
```

**参数:**
- `task`: 用户任务描述
- `max_iterations`: 最大迭代次数（可选）
- `on_iteration`: 每次迭代完成后的回调函数
- `on_model_stream`: 模型流式输出回调
- `on_transparent_enter`: 进入透明模式的回调
- `on_transparent_exit`: 退出透明模式的回调

**返回:** AI 思考结果或完成信息

#### stop() 方法

停止当前执行的任务。

```python
stop() -> None
```

### execute_task() 便捷函数

快速执行任务的便捷函数。

```python
execute_task(
    task: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
    max_iterations: Optional[int] = None,
) -> str
```

**参数:**
- `task`: 用户任务描述
- `api_key`: API 密钥（可选）
- `base_url`: API 基础地址（可选）
- `model_name`: 模型名称（可选）
- `max_iterations`: 最大迭代次数（可选）

**返回:** AI 思考结果或完成信息

## 使用示例

### 示例 1: 简单任务（使用便捷函数）

```python
from baodou_ai import execute_task

result = execute_task(
    "打开记事本",
    api_key="your_api_key"
)
print(result)
```

### 示例 2: 使用 BaodouAI 类

```python
from baodou_ai import BaodouAI

ai = BaodouAI(
    api_key="your_api_key",
    base_url="https://api.example.com",
    model_name="your_model"
)

result = ai.execute(
    "打开浏览器并访问百度",
    max_iterations=20
)
print(result)
```

### 示例 3: 使用回调函数

```python
from baodou_ai import BaodouAI

ai = BaodouAI(api_key="your_api_key")

def on_iteration(idx, info):
    print(f"[迭代 {idx}] 思考: {info['thinking']}")
    print(f"          操作: {info['action']} @ {info['coordinates']}")

def on_model_stream(iteration, chunk):
    print(f"[模型第 {iteration + 1} 轮]", chunk, end="")

def on_transparent_enter():
    print("→ 进入透明模式")

def on_transparent_exit():
    print("← 退出透明模式")

result = ai.execute(
    "打开计算器",
    max_iterations=15,
    on_iteration=on_iteration,
    on_model_stream=on_model_stream,
    on_transparent_enter=on_transparent_enter,
    on_transparent_exit=on_transparent_exit
)
```

### 示例 4: 停止正在执行的任务

```python
from baodou_ai import BaodouAI
import threading
import time

ai = BaodouAI(api_key="your_api_key")

def stop_after_delay():
    time.sleep(10)  # 10 秒后停止
    print("正在停止任务...")
    ai.stop()

stop_thread = threading.Thread(target=stop_after_delay)
stop_thread.start()

result = ai.execute(
    "执行一个长时间任务",
    max_iterations=30
)
print(result)
```

## 命令行使用

### 基本用法

```bash
python -m baodou_ai.cli "任务描述" --api-key YOUR_KEY
```

### 命令行参数

| 参数 | 简写 | 说明 |
|------|------|------|
| `task` | - | 要执行的任务描述（必需） |
| `--api-key` | `-k` | API 密钥 |
| `--base-url` | `-u` | API 基础地址 |
| `--model-name` | `-m` | 模型名称 |
| `--max-iterations` | `-i` | 最大迭代次数 |
| `--version` | `-v` | 显示版本信息 |

### 命令行示例

```bash
# 简单任务
python -m baodou_ai.cli "打开浏览器" --api-key YOUR_KEY

# 指定最大迭代次数
python -m baodou_ai.cli "打开记事本" --api-key YOUR_KEY --max-iterations 10

# 指定 API 地址
python -m baodou_ai.cli "关闭窗口" --api-key YOUR_KEY --base-url https://api.example.com
```

## 当前项目结构

```
project-root/
├── src/baodou_ai/
│   ├── __init__.py
│   ├── __main__.py
│   ├── api.py
│   ├── cli.py
│   ├── agent/
│   ├── ai/
│   ├── core/
│   ├── gui/
│   └── platform/
├── examples/
│   └── api_example.py
├── docs/
│   ├── API_USAGE.md
│   ├── INTEGRATION_GUIDE.md
│   └── PERFORMANCE_ANALYSIS.md
├── tests/
├── config.json
└── pyproject.toml
```

## 注意事项

1. **API Key 安全**: 不要将 API Key 提交到代码仓库
2. **权限**: 确保程序有足够的屏幕截图和鼠标键盘控制权限
3. **配置文件**: 如果配置文件中已设置 API Key，可以省略 `--api-key` 参数
4. **透明模式**: API 内部会自动处理透明穿透模式，无需额外配置

## 更多示例

请参考 `examples/api_example.py` 获取更多使用示例。
