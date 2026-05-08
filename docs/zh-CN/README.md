# 同窗项目说明书

这套文档承接原本 README 里的详细内容。README 现在主要作为 GitHub 首页，保留产品介绍、流程图和快速开始；更细的配置、架构、语音、API、开发与安全说明放在这里。

## 文档目录

| 文档 | 内容 |
| --- | --- |
| [产品概览](product-overview.md) | 产品定位、核心能力、运行形态和当前状态。 |
| [安装与配置](setup-configuration.md) | Python 环境、安装方式、模型配置、平台差异、本地唤醒词模型。 |
| [语音交互](voice-interaction.md) | 唤醒词、实时 ASR、VAD、回声消除、语音口令、插话和 TTS。 |
| [CLI 与 Python API](usage-cli-api.md) | `coview-cli`、`CoViewAI`、回调和集成示例。 |
| [架构说明](architecture.md) | 仓库结构、入口层、控制循环、GUI、平台、语音和后台 Code Agent。 |
| [Agent 协议](agent-protocol.md) | 模型响应分支、工具调用、`page_loading`、`respond`、过程汇报和记忆字段。 |
| [开发指南](development.md) | 测试命令、格式化、手动验收、阅读顺序和扩展点。 |
| [安全与贡献](safety-contributing.md) | 桌面自动化安全提示、隐私边界和贡献建议。 |

## 已有深度文档

- [架构流程图](../COVIEW_FLOW.md)
- [简化运行流程](../COVIEW_FLOW_SIMPLE.md)
- [语音交互流程](../COVIEW_VOICE_FLOW.md)
- [集成指南](../INTEGRATION_GUIDE.md)
- [性能分析](../PERFORMANCE_ANALYSIS.md)
- [平台验收文档](../平台验收/平台能力矩阵.md)

