# 许可适用范围

本项目中维护者有权授权的项目代码、原创文档与配置，以 **GNU Affero General Public License v3.0 or later（AGPL-3.0-or-later）** 提供。根 LICENSE 保留既有 AGPL v3 全文，正文没有改写；本文件说明适用对象及“or later”选择。维护者的明确授权依据见 AUTHORIZATION.md。

## 项目范围

下表中的项目工作适用上述 AGPL 声明；引用、参考和潜在上游部分的版权及许可通知继续保留，不因本声明消失。没有逐文件版权头不等于未授权，也不表示可以忽略第三方权利。

| 文件或内容 | 范围及来源 |
|---|---|
| 根目录全部 .py、.cmd 脚本 | 转录、排谱、门控、语义分析、下载器、诊断、验证、测试和评测等项目代码；主要通过公开 API 调用另行安装的依赖 |
| semantic_frontend.py | 已有 AGPL-3.0-or-later；参考 Essentia 的 TensorflowInputMusiCNN、TriangularBands、Slaney 转换及 Windowing；保留 UPF 版权、无担保和差异说明 |
| music_scribe.py 调性模板 | Krumhansl 与 Temperley 公开算法模板；可在 Essentia Key / music21 对照到相应数值，不能宣传成自研模型。来源见 SOURCE_AUDIT.md |
| _vendor/dora/*.py | 项目本地最小接口替身；与上游完整日志实现不同。接口来源及上游 MIT 通知见 THIRD_PARTY_NOTICES.md / THIRD_PARTY_LICENSES/dora-MIT.txt |
| tools/reference_frontend.cjs | 项目编写的验证调用脚本；其加载的官方 Essentia.js 不在源码包内，官方参考包适用自身 AGPL 声明 |
| 根目录 Markdown、requirements*.txt、项目配置及来源记录 | 项目撰写的内容适用 AGPL；其中引用的第三方通知和法律文本保留自身条款 |
| tests/fixtures/frontend_fixture.npz | 合成输入帧与 Essentia.js 参考输出，按项目 AGPL 路线提供并保留上游说明；不含真实音乐或讲话波形，不代表真实识别准确率 |
| samples/README.md、SAMPLES.json | 项目编写的运行说明和来源清单；清单中的第三方录音各自适用其来源条款，录音不随包分发 |

## 不由根许可证重新覆盖的内容

- models/ 下的官方元数据、标签表、模型许可原文：保留来源与各自条款。项目自编 models/manifest.json 是事实记录，不是新的模型授权。
- models/LICENSE*.txt、THIRD_PARTY_LICENSES/ 下的上游许可与通知：按原文本保留。
- 六份外部语义权重、Basic Pitch 模型、可选 Demucs 权重、Python 依赖及原生库：不在本源码包内，安装或下载取得后适用各自条款。
- 用户输入音频、生成的谱面/MIDI、原始作品、字体和第三方数据集：不因运行项目自动取得授权，不因生成文件自动套用项目许可证。

AGPL 代码本身允许商业使用；本版“本地非商业”安排针对当前包含 NC 模型的使用方案，不是对 AGPL 添加限制。公开分发受 AGPL 覆盖的修改版本时，应保留通知、说明修改并按条款提供源码；提供修改版本的网络交互服务时，还须满足第 13 条对应源码要求。这里没有把独立第三方材料一概认定为同一衍生作品。

SOURCE_PROVENANCE.json 和 MANIFEST.json 记录文件来源与完整性，不单独证明原创。有限来源核对见 SOURCE_AUDIT.md；未决的 MTG SA/ND 声明见 LICENSE_STATUS.md。
