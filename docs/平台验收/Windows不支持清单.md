# Windows 平台不支持清单

## 目的

本文基于当前仓库中的源码、平台能力矩阵、Windows 手动回归清单整理，目的是明确：

1. 当前版本在 Windows 上**明确不支持**的能力。
2. 当前版本在 Windows 上**仅部分支持**或虽然能运行、但明显按 macOS 语义设计，导致体验不佳或容易失效的能力。
3. 哪些问题会直接影响“打开各种软件”“管理文件夹”等你当前最关心的场景。

说明：

- 本文只统计**仓库中可以明确确认**的问题，不臆测未落地的需求。
- “不支持”优先以源码中的显式报错 / `None` 返回 / 文档矩阵定义为准。
- “效果不好”类问题会单独列出，避免和“完全不支持”混在一起。

## 总结

当前项目并不是“完全不支持 Windows”，但 Windows 端存在一批明显缺口，尤其集中在平台集成层：

- `open_app_launcher` 在 Windows 上明确不支持。
- `read_current_document` 在 Windows 上已适配 V1，但仍是明显降级方案。
- `get_active_document_path` 在 Windows 上已补齐 P0，支持 Explorer 与 Office/WPS，但仍有应用范围边界。
- `move_to_trash` 在 Windows 上已支持，但仍缺少更细粒度的用户确认与批量删除体验优化。
- `activate_app` 在 Windows 上已补为优先按 `hwnd`、回退按 `pid` 的 best-effort 前台恢复，但仍受系统前台焦点限制影响。
- `manage_files` 已支持在 Windows 资源管理器前台使用，但第三方文件管理器仍不在支持范围内。
- Windows 悬浮窗虽有专门适配，但部分 Win32 原生 region/形状能力没有实现完全。

## 一、明确不支持的能力

### 1. 打开应用启动器 `open_app_launcher`

- Windows 状态：**不支持**
- 影响场景：当用户说“打开启动器/应用列表/应用搜索”时，Windows 无法像 macOS Launchpad 那样处理。
- 代码证据：
  - `src/baodou_ai/platform/windows.py`
  - 直接抛错：`raise RuntimeError("open_app_launcher 仅支持 macOS。")`
- 文档证据：
  - `docs/平台验收/平台能力矩阵.md` 中，`open_app_launcher` 的 Windows 状态是 `不支持`
  - `docs/平台验收/Windows手动回归清单.md` 中，`WIN-PLT-04` 明确要求返回“不支持”视为通过

## 二、部分支持或明显退化的能力

### 1. 恢复外部应用焦点 `activate_app`

- Windows 状态：**部分支持**
- 实际情况：
  - 已支持优先按记录下来的 `hwnd` 恢复具体窗口，找不到时再回退按 `pid` 查找目标顶层窗口
  - 如果窗口最小化，会先执行恢复
  - 普通 `SetForegroundWindow` 失败时，会走线程附着兜底
- 代码证据：
  - `src/baodou_ai/platform/windows.py`
  - 通过按 `pid` 枚举顶层窗口、`ShowWindow(SW_RESTORE)`、`SetForegroundWindow`、`AttachThreadInput` 组合实现
- 连锁影响：
  - 自动化截图前如果发现焦点不在目标应用，会尝试恢复
  - 相比之前“直接失败”的状态，现在可明显减少需要用户手动点击目标窗口的场景
- 关联代码：
  - `src/baodou_ai/core/observation.py`
- 文档证据：
  - `docs/平台验收/平台能力矩阵.md` 中，`activate_app` 的 Windows 状态是 `部分支持`
- 限制说明：
  - 仍受 Windows 前台锁、权限边界、某些全屏/受保护窗口限制影响
  - 因此依旧不能承诺 100% 成功，只能视为 best-effort 恢复

### 2. 获取当前活动文档路径 `get_active_document_path`

- Windows 状态：**部分支持**
- 实际情况：
  - 已支持获取当前前台 File Explorer 窗口的本地目录路径
  - 已支持获取当前前台 Word / Excel / PowerPoint / WPS 文档路径
  - 文档未保存或资源管理器停留在“此电脑/快速访问”等非文件系统位置时返回空字符串
- 代码证据：
  - `src/baodou_ai/platform/windows.py`
  - 通过 PowerShell/COM 查询活动 Office/WPS 文档与前台 Explorer 目录
- 连锁影响：
  - `core/observation.py` 已可在 Windows 上为前台文档或文件夹补充路径提示
  - `manage_files` 省略路径时，已可复用当前 Explorer 目录作为上下文
- 限制说明：
  - 当前不覆盖 VSCode / JetBrains / Notepad 等编辑器类当前文件路径
  - 第三方文件管理器仍不在支持范围内

### 3. 移到废纸篓 / 回收站 `move_to_trash`

- Windows 状态：**已支持**
- 实际情况：
  - 已通过 Windows Shell API 将文件或目录移入系统回收站
  - 删除语义不再是“永久删除”，与 macOS 的废纸篓设计对齐
- 代码证据：
  - `src/baodou_ai/platform/windows.py`
  - 通过 `SHFileOperationW` + `FOF_ALLOWUNDO` 调用系统回收站能力
- 限制说明：
  - 当前默认静默执行，不弹系统确认框
  - 更细粒度的用户确认、批量删除交互和撤销提示仍可继续优化

### 3. 读取当前文档 `read_current_document`

- Windows 状态：**部分支持**
- 实际情况：
  - Windows 已支持 copy-based V1 提取，不再是平台层直接拒绝
  - 对 Word/WPS/纯文本编辑器可直接尝试 `Ctrl+A` + `Ctrl+C`
  - 对 VSCode / Cursor / JetBrains / TRAE 等 IDE 仍然要求传入 `screen_index` 和 `position`
  - `chunk / next / search` 可复用已提取全文
  - `follow_view` 在 Windows V1 仍未实现，只更新文本上下文，不执行视觉跳转
- 代码证据：
  - `src/baodou_ai/core/automation_tools/document_reader.py`
  - 已改为仅在非 macOS / Windows 平台返回 `read_current_document_not_supported_platform`
  - Windows 会复用现有复制提取链路，并在 `follow_view` 时明确返回“Windows V1 暂不支持文档视觉跳转”
- 限制说明：
  - 这仍然不是 COM / UI Automation 级别的结构化读取
  - 如果前台焦点不对、复制失败、或者取到工具栏文本，仍会降级为重试或截图分析

### 2. 前台应用识别

- Windows 状态：**部分支持**
- 实际情况：
  - Windows 当前通过 `GetForegroundWindow + GetWindowTextW` 取前台窗口
  - 返回的 `app_name` 本质上更像“窗口标题”，不是真正稳定的应用名
- 代码证据：
  - `src/baodou_ai/platform/windows.py`
  - `get_frontmost_app_info()` 返回：
    - `app_name = title`
    - `bundle_id = ""`
    - `identifier = title or pid`
- 影响：
  - 前台应用识别精度不如 macOS
  - 对需要识别“当前是不是资源管理器/某个特定应用”的工具尤其不友好
- 文档证据：
  - `docs/平台验收/平台能力矩阵.md` 中，`前台应用识别` 的 Windows 状态是 `部分支持`

### 3. 设置窗口行为退化

- Windows 状态：**有意降级**
- 具体表现：
  - 设置窗口在 Windows 上默认**不置顶**
  - 关闭窗口时在 Windows 上默认**直接关闭，不隐藏到后台**
- 代码证据：
  - `src/baodou_ai/gui/control_console.py`
  - `_use_topmost_window()` 在 Windows 返回 `False`
  - `_hide_instead_of_close()` 在 Windows 返回 `False`
- 影响：
  - 行为与 macOS 不一致
  - 对用户来说更像“能力退化”，不是纯视觉差异

### 4. 悬浮菜单确认逻辑退化

- Windows 状态：**有意降级**
- 具体表现：
  - Windows 下清空历史、关闭应用时跳过确认弹窗
- 代码证据：
  - `src/baodou_ai/gui/floating/menu_controller.py`
  - `_skip_confirmation_dialogs()` 在 Windows 返回 `True`
- 影响：
  - 交互保护比 macOS 弱
  - 更容易出现误操作

## 三、Windows 上“效果不好”的高风险点

这一部分不一定全部属于“文档已定义为不支持”，但从实现看，确实是当前 Windows 体验差的主要来源。

### 1. Windows 文件管理能力仍有剩余短板

- 问题等级：**高**
- 原因：
  - 虽然 `manage_files` 已支持在 `File Explorer` 前台使用
  - 且删除安全语义已由 `move_to_trash` 补齐
  - 但当前只覆盖系统资源管理器，不覆盖第三方文件管理器
- 代码证据：
  - `src/baodou_ai/core/automation_tools/file_tools.py`
  - 已扩展为同时识别 `Finder/访达` 和 `File Explorer/Explorer/资源管理器`
  - 省略路径时会通过 `get_active_document_path()` 获取当前文件管理器目录
- 连锁影响：
  - `list`
  - `search`
  - `create`
  - `delete`
  - `rename`
  - `move`
  这些围绕“当前文件夹上下文”的操作已比之前完整，但第三方文件管理器仍不在支持范围内

### 2. 编辑器类当前文件路径仍未覆盖

- 问题等级：**高**
- 原因：
  - 当前 `get_active_document_path()` 仅覆盖 Explorer、Word、Excel、PowerPoint、WPS
  - 对 VSCode / Cursor / JetBrains / Notepad 等编辑器类应用仍返回 `None`
- 代码证据：
  - `src/baodou_ai/platform/windows.py`
- 影响：
  - 前台提示词对代码编辑器和纯文本编辑器仍无法稳定补充 `Current file path`
  - 这部分能力仍明显弱于 macOS 的 AppleScript 文档路径查询

### 3. 打开应用仅实现了“按路径启动”，没有 Windows 原生启动器语义

- 问题等级：**中高**
- 原因：
  - Windows `launch_app` 的主逻辑是匹配本地应用路径后用 `os.startfile` / `subprocess.Popen` 启动
  - 但没有类似 macOS Launchpad 的系统级应用启动器集成
- 代码证据：
  - `src/baodou_ai/platform/windows.py`
  - `launch_app()` 可启动命中应用
  - `open_app_launcher()` 明确不支持
- 影响：
  - “打开某个软件”在命中路径时可以工作
  - 但“打开应用列表 / 打开启动器 / 通过系统级入口搜索程序”这一类体验明显缺失

### 4. 自动化执行前的焦点恢复能力不足

- 问题等级：**中高**
- 原因：
  - 自动化观察链路依赖“截图前恢复正确前台应用”
  - 但 Windows `activate_app()` 未实现
- 代码证据：
  - `src/baodou_ai/platform/windows.py`
  - `src/baodou_ai/core/observation.py`
- 影响：
  - 用户切换多个窗口后，任务更容易依赖人工纠正焦点
  - 会放大“识别错窗口”“操作错上下文”的风险

### 5. Windows 悬浮窗的原生 region/形状能力未补齐

- 问题等级：**中**
- 原因：
  - 项目为 Windows 单独写了浮窗适配层
  - 但 `clear_region`、`apply_ellipse_region`、`apply_round_rect_region` 都直接返回 `False`
- 代码证据：
  - `src/baodou_ai/gui/floating/windows_native.py`
- 说明：
  - 这不代表悬浮窗完全不可用
  - 但说明 Windows 上原生窗口裁剪、形状、点击区域等细节能力没有做完
- 影响：
  - 可能出现“能用，但不够稳/不够像原生”的情况

## 四、按用户关心场景归纳

### 1. 打开各种软件

当前 Windows 表现分成两层：

- `launch_app`：**可用，但偏基础**
  - 本质是匹配可执行路径后启动
- `open_app_launcher`：**明确不支持**
  - 无法像 macOS 一样调起启动器 / Launchpad 类入口

结论：

- “直接打开某个已知软件”有一定可用性
- “打开应用启动器、依赖系统级应用入口搜索软件”当前不支持

### 2. 管理文件夹

这是当前 Windows 体验最差的一块，原因是多个问题叠加：

- `manage_files` 的入口语义写死为 Finder/访达
- Windows 无法稳定识别资源管理器为目标应用
- Windows 无法获取当前资源管理器目录路径
- Windows 不支持 `move_to_trash`

结论：

- 文件管理相关工具虽然不是每个子操作都显式报“Windows 不支持”
- 但整体设计仍强依赖 macOS/Finder 语义，所以在 Windows 上大概率“不顺手、容易失败、上下文不准”

### 3. 读取当前文档/文件内容

- `read_current_document` 在 Windows 上已支持 V1 copy-based 提取，但仍有明显限制
- `get_active_document_path` 在 Windows 上明确不支持

结论：

- 任何依赖“从当前文档窗口读取正文 / 推导当前文件路径”的能力，Windows 目前仍弱于 macOS

## 五、现有文档中已经承认的 Windows 边界

仓库里其实已经有一部分 Windows 边界说明，只是分散在多个地方：

- `docs/平台验收/平台能力矩阵.md`
  - 明确标记了 `open_app_launcher`、`get_active_document_path`、`move_to_trash` 的 Windows 状态
  - 明确标记了 `activate_app`、`前台应用识别` 的 Windows 为 `部分支持`
- `docs/平台验收/Windows手动回归清单.md`
  - 已把 `open_app_launcher` 返回“不支持”定义为正确结果
- `src/baodou_ai/platform/windows.py`
  - 直接体现了多个未实现点
- `src/baodou_ai/core/automation_tools/document_reader.py`
  - 直接体现了文档读取的 macOS-only 限制

## 六、优先级建议

如果后续要优先补 Windows，我建议按下面顺序做：

### P0

- 实现 Windows 的 `activate_app`
- 实现 Windows 的 `get_active_document_path`
- 把 `manage_files` 从 Finder 语义改为“资源管理器 / 显式路径双模式”

### P1

- 实现 Windows 的 `move_to_trash`
- 为 Windows 增加“资源管理器当前目录识别”
- 改造 `get_frontmost_app_info()`，不要再把窗口标题直接当 `app_name`

### P2

- 评估 Windows 是否需要一个 `open_app_launcher` 的替代能力
- 补齐悬浮窗 region/形状相关 Win32 能力
- 统一 Windows 与 macOS 的设置窗口 / 右键菜单交互差异

## 七、结论

如果只看当前仓库，Windows 端最明显的问题不是“完全不能跑”，而是：

- 一部分关键能力明确没做完
- 一部分工具仍然按 macOS/Finder 语义设计
- 一部分自动化链路在 Windows 上只能走降级方案

所以你的体感“打开各种软件、管理文件夹等工具在 Windows 上效果不好”是有明确代码依据的，而且核心问题基本已经能定位到：

- `platform/windows.py`
- `core/automation_tools/file_tools.py`
- `core/automation_tools/document_reader.py`
- `core/observation.py`
- `gui/floating/windows_native.py`
