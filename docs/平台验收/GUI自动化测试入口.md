# GUI 自动化测试入口

## 统一入口

统一使用：

```bash
venv/bin/python scripts/run_gui_acceptance.py
```

默认行为：
- 按 `gui -> platform -> capability` 顺序执行
- 每个 suite 独立超时控制（默认 `240` 秒）
- 默认设置 `QT_QPA_PLATFORM=offscreen`
- 任一 suite 失败或超时立即停止，返回非 0

## Suite 说明

- `gui`
  - `tests/test_floating_window.py`
  - `tests/test_log_window.py`
- `platform`
  - `tests/test_platform_macos.py`
  - `tests/test_platform_windows.py`
  - `tests/test_platform_common.py`
- `capability`
  - `test_automation.py` 与 `test_runner.py` 中截图/前台识别/打开应用/打开文件/打开 URL 关键用例

## 常用命令

```bash
# 只跑 GUI
venv/bin/python scripts/run_gui_acceptance.py --suite gui

# 只跑平台适配
venv/bin/python scripts/run_gui_acceptance.py --suite platform

# 只跑能力链路关键用例
venv/bin/python scripts/run_gui_acceptance.py --suite capability

# 跑全部
venv/bin/python scripts/run_gui_acceptance.py --suite all
```

## 超时与防卡住

```bash
# 验证超时机制（故意设小）
venv/bin/python scripts/run_gui_acceptance.py --suite gui --timeout-seconds 1
```

预期：
- 输出 `Likely stuck suite: <suite_name>`
- 返回码 `124`

## Offscreen 切换

默认强制 `offscreen`。如需真实窗口模式，手动关闭：

```bash
venv/bin/python scripts/run_gui_acceptance.py --suite gui --no-offscreen
```

