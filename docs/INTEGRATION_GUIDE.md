# 包豆电脑 - 项目集成指南

本文档详细说明如何从零开始，将包豆电脑集成到你的项目中。

---

## 目录

1. [第一步：克隆项目](#第一步克隆项目)
2. [第二步：安装依赖](#第二步安装依赖)
3. [第三步：配置 API 密钥](#第三步配置-api-密钥)
4. [第四步：在其他项目中调用](#第四步在其他项目中调用)
5. [完整示例](#完整示例)
6. [常见问题](#常见问题)

---

## 第一步：克隆项目

### 方法一：使用 Git 克隆（推荐）

打开终端（命令行），输入以下命令：

```bash
# 进入你想存放项目的目录
cd C:\你的项目目录

# 克隆项目
git clone https://github.com/mini-yifan/baodou_ai2.0_mac.git

# 进入项目文件夹
cd baodou_ai2.0_mac
```

### 方法二：直接下载 ZIP

1. 打开浏览器，访问：`https://github.com/mini-yifan/baodou_ai2.0_mac`
2. 点击绿色的 **Code** 按钮
3. 选择 **Download ZIP**
4. 解压到你想要的位置

---

## 第二步：安装依赖

### 2.1 创建虚拟环境（推荐）

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 2.2 安装项目

```bash
# 进入项目目录
cd C:\你的路径\baodou_ai2.0_mac

# 安装项目（这会自动安装所有依赖）
pip install -e .
```

**说明**：`-e` 表示"可编辑模式"，这样你修改源码后会立即生效。

---

## 第三步：配置 API 密钥

包豆电脑需要 API 密钥才能调用 AI 模型。

### 3.1 获取 API 密钥

1. 访问：`https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey`
2. 登录/注册账号
3. 创建 API 密钥

### 3.2 配置方式

**方式一：在代码中直接传入（最简单）**

```python
from baodou_ai import BaodouAI

# 直接传入 API 密钥
ai = BaodouAI(api_key="你的API密钥")
```

**方式二：使用配置文件**

在项目根目录创建 `config.json` 文件：

```json
{
    "api_config": {
        "api_key": "你的API密钥",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model_name": "你的模型名称"
    }
}
```

---

## 第四步：在其他项目中调用

### 4.1 最简单的调用方式

```python
from baodou_ai import execute_task

# 一行代码执行任务
result = execute_task(
    "打开记事本",
    api_key="你的API密钥"
)

print(result)
```

### 4.2 使用类的方式（推荐）

```python
from baodou_ai import BaodouAI

# 创建 AI 控制器
ai = BaodouAI(api_key="你的API密钥")

# 执行任务
result = ai.execute("打开浏览器并访问百度")

print(result)
```

### 4.3 在其他项目目录中调用

假设你的项目结构如下：

```
C:\我的项目\
├── main.py          # 你的主程序
└── venv/            # 你的虚拟环境
```

**方法一：安装包豆电脑到你的虚拟环境**

```bash
# 在你的项目目录中
cd C:\我的项目

# 激活虚拟环境
venv\Scripts\activate

# 安装包豆电脑
pip install -e C:\路径\baodou_ai2.0_mac
```

然后在 `main.py` 中：

```python
from baodou_ai import BaodouAI

ai = BaodouAI(api_key="你的密钥")
result = ai.execute("打开计算器")
```

**方法二：添加路径到 sys.path**

```python
import sys
sys.path.insert(0, r"C:\路径\baodou_ai2.0_mac\src")

from baodou_ai import BaodouAI

ai = BaodouAI(api_key="你的密钥")
result = ai.execute("打开计算器")
```

---

## 完整示例

### 示例 1：基础使用

```python
"""
最简单的使用示例
"""
from baodou_ai import execute_task

# 执行任务
result = execute_task(
    task="打开记事本",
    api_key="你的API密钥"
)

print(f"执行结果: {result}")
```

### 示例 2：带回调的使用

```python
"""
带回调函数的使用示例 - 可以看到每一步的执行情况
"""
from baodou_ai import BaodouAI

def on_iteration(index, info):
    """每次迭代都会调用这个函数"""
    print(f"第 {index} 次操作:")
    print(f"  思考: {info['thinking']}")
    print(f"  操作: {info['action']}")
    print(f"  坐标: {info['coordinates']}")
    print()

# 创建控制器
ai = BaodouAI(api_key="你的API密钥")

# 执行任务，并传入回调函数
result = ai.execute(
    "打开计算器",
    max_iterations=15,
    on_iteration=on_iteration
)

print(f"最终结果: {result}")
```

### 示例 3：集成到现有项目

```python
"""
集成到现有项目的示例
"""
import sys

# 添加包豆电脑的路径（如果需要）
sys.path.insert(0, r"C:\baodou_ai2.0_mac\src")

from baodou_ai import BaodouAI

class MyAutomationApp:
    def __init__(self, api_key):
        self.ai = BaodouAI(api_key=api_key)
    
    def run_task(self, task_description):
        """执行自动化任务"""
        print(f"开始执行: {task_description}")
        
        result = self.ai.execute(
            task_description,
            max_iterations=20
        )
        
        print(f"执行完成: {result}")
        return result
    
    def stop(self):
        """停止当前任务"""
        self.ai.stop()

# 使用
if __name__ == "__main__":
    app = MyAutomationApp(api_key="你的API密钥")
    app.run_task("打开浏览器")
```

### 示例 4：命令行使用

```bash
# 基本用法
python -m baodou_ai.cli "打开记事本" --api-key 你的密钥

# 指定最大迭代次数
python -m baodou_ai.cli "打开浏览器" --api-key 你的密钥 --max-iterations 10

# 查看帮助
python -m baodou_ai.cli --help
```

---

## 常见问题

### Q1: 提示找不到模块 `baodou_ai`

**解决方法**：

```bash
# 确保在正确的环境中
pip install -e C:\路径\baodou_ai2.0_mac
```

或者在代码中添加路径：

```python
import sys
sys.path.insert(0, r"C:\路径\baodou_ai2.0_mac\src")
```

### Q2: 提示 API 密钥错误

**检查清单**：
1. 确认密钥是否正确复制（没有多余空格）
2. 确认账户是否有余额
3. 确认模型名称是否正确

### Q3: 鼠标键盘操作没有反应

**可能原因**：
1. 程序没有管理员权限
2. 被其他软件拦截（如杀毒软件）
3. 目标窗口被最小化

**解决方法**：
- 以管理员身份运行
- 关闭或添加信任到杀毒软件
- 确保目标窗口可见

### Q4: 如何停止正在执行的任务？

```python
import threading
import time

ai = BaodouAI(api_key="你的密钥")

# 在另一个线程中执行
def run_task():
    result = ai.execute("一个长时间任务")
    print(result)

thread = threading.Thread(target=run_task)
thread.start()

# 10秒后停止
time.sleep(10)
ai.stop()
```

### Q5: 支持哪些操作类型？

| 操作 | 说明 |
|------|------|
| `click` | 单击 |
| `double_click` | 双击 |
| `long_press` | 长按 |
| `right_click` | 右键点击 |
| `drag` | 拖拽 |
| `scroll_up` | 向上滚动 |
| `scroll_down` | 向下滚动 |
| `hotkey` | 快捷键 |
| `launch_app` | 启动或激活应用 |
| `open_app_launcher` | 打开应用启动器 |
| `open_in_browser` | 用默认浏览器打开网址或搜索 |
| `open_in_finder` | 在访达中打开指定目录（默认桌面）；传入文件路径时打开所在文件夹并选中 |
| `read_current_page` | 提取当前网页正文 |
| `read_current_document` | 提取当前文档或代码正文 |
| `hold_modifier_keys` | 跨多步保持修饰键 |
| `release_modifier_keys` | 释放修饰键 |
| `input_text` | 统一文本输入；可直接输入，也可先点击输入框；支持 `replace=true` 全选替换、`submit=true` 回车提交 |

---

## 快速参考卡片

```python
# 导入
from baodou_ai import BaodouAI, execute_task

# 方式一：便捷函数
result = execute_task("任务描述", api_key="密钥")

# 方式二：类实例
ai = BaodouAI(api_key="密钥")
result = ai.execute("任务描述", max_iterations=15)

# 方式三：带回调
ai.execute("任务", on_iteration=lambda i, info: print(info))

# 停止任务
ai.stop()

# 命令行
# python -m baodou_ai.cli "任务" --api-key 密钥
```

---

## 需要帮助？

如果遇到问题，请检查：
1. API 密钥是否正确
2. 依赖是否安装完整
3. 是否有足够的权限

祝你使用愉快！🎉
