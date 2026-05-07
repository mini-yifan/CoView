# 同窗当前链路性能分析

## 1. 分析范围

本文档基于 2026 年 4 月 9 日仓库现状，分析当前真实主链路的性能热点：

```text
GUI / CLI / API
  -> ControlLoopRunner
  -> AIClient.get_next_action_from_capture()
  -> ToolExecutor
  -> AutomationController
```

说明：

- 旧版 `_execute_control` 已不再是当前主执行路径，本报告不再围绕那条历史链路展开。
- 当前性能分析以“单轮循环的真实热路径”为准，不讨论功能层面的架构重写。

## 2. 当前主要耗时来源

### 2.1 模型请求仍是最大头

当前单轮最重的步骤仍然是视觉模型调用，包括：

- 请求准备
- 上下文拼装
- 图片随消息发送
- 远端模型推理
- 流式首包等待

代码侧已有可观测指标：

- `encode_ms`
- `request_prepare_ms`
- `model_latency_ms`
- `first_chunk_ms`

结论：

- 第三轮不尝试解决网络和模型本身的延迟。
- 第三轮只优化本地热路径，避免把“流畅性升级”做成高风险协议或产品改造。

### 2.2 本地热路径的重复成本

在模型之外，当前最值得优化的是以下几类重复成本：

- `runner` 每轮重复读取 `memory.txt`
- `changed_pixels_ratio` 每轮重复对 PNG 做灰度解码
- 默认浏览器提示每轮重复走平台查询
- GUI 模型流输出和日志窗口在高频 chunk 下过于频繁地刷新 `QTextEdit`

这些问题单项开销不一定压过模型请求，但它们会直接影响：

- GUI 卡顿感
- 流式输出顺滑度
- 主循环中的额外 CPU / I/O 浪费
- 停止、报错、收尾时的尾部文本丢失风险

## 3. 当前已落地的低风险优化

第三轮已在不改变协议和对外行为的前提下完成以下优化：

### 3.1 Runner 热路径缓存

- 为单次任务引入 remember 文本运行态缓存。
- 首轮仍按现状从磁盘读取；后续轮次复用内存缓存。
- remember 成功写入后同步更新缓存，磁盘落盘行为保留。
- 清任务时同步清空缓存，保证任务边界不串数据。

### 3.2 灰度图解码缓存

- `changed_pixels_ratio` 改为复用最近两轮相关 bundle 的灰度图。
- 避免对上一轮和当前轮截图重复 `cv2.imdecode`。
- 缓存仅保留最近两轮相关帧，防止运行期内存无界增长。

### 3.3 UI 刷新节流

- 主窗口模型流输出改为短周期批量 flush。
- 日志窗口改为短周期批量 flush。
- 任务结束、报错、关闭窗口前会强制 flush，降低尾部文本丢失风险。
- 输出内容、顺序、标题、日志级别保持不变。

### 3.4 AIClient 小步缓存

- 默认浏览器提示改为按 client 生命周期缓存。
- 仅优化当前真实热路径 `get_next_action_from_capture()` 所依赖的重复查询。
- 不重写 `analyze_screen()` / `get_next_action()` 的旧路径。

## 4. 当前建议关注的指标

后续继续观察流畅性时，优先看这些现有指标：

- `capture_ms`
- `changed_pixels_ratio`
- `encode_ms`
- `request_prepare_ms`
- `model_latency_ms`
- `first_chunk_ms`
- `settle_ms`
- `execute_ms`
- `loop_total_ms`

推荐口径：

- 用 `loop_total_ms` 观察单轮总体变化。
- 用 `encode_ms` 和 `capture_ms` 观察本地热路径是否继续放大。
- 用 `first_chunk_ms` 观察流式首包体感。
- 用 GUI 手动回归确认节流后界面是否更顺、是否有尾部文本遗漏。

## 5. 当前结论

- 当前系统的绝对耗时上限仍主要受模型请求影响。
- 第三轮已经把本地热路径里最稳、最值得做的重复成本收掉了一批。
- 后续如果继续做性能工作，优先级应是：
  1. 基于现有指标补更稳定的性能观测
  2. 继续压缩 `runner` / `automation` 内部不必要的中间态工作
  3. 仅在证据充分时再考虑更大粒度的结构重组

当前明确不建议在没有额外基准数据前直接做：

- 调整 `settle_*` 默认值
- 大规模重写 `AIClient`
- 拆 `automation.py` 的同时混入性能优化
- 改 agent 协议或 UI 对外行为
