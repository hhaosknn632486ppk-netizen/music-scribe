# 外部代码与许可来源核对

日期：2026-10-23。对象：public-source-license-review-1，来自保留的 public-source-preview-1 / 1.3.0。维护者已明确确认个人项目、无其他真人贡献者、沿用 AGPL，本版采用本地非商业模型使用方案。依据见 AUTHORIZATION.md；这不替第三方内容作授权。

## 当前结论

在本次可见源码和选定上游对照范围内，未发现一个必须新增个别授权才能保留的具体代码片段。现有公开许可、保留通知和明确分发边界可以支持继续整理源码候选，不把联系权利人作为当前前置。此结论有检查范围限制，不能改写为“已证明所有代码完全原创、所有依赖已完整审计、全部功能可商用”。

项目代码授权范围已经明确；MTG 模型 SA/ND 冲突仍未获官方澄清，以原始权重、本地非商业使用、不分发权重的方式管理范围。两项不能都标作“许可证问题已彻底解决”。

## 检查方法与发现

全部 24 份 Python 文件、合计 3956 行（前一候选），已解析 AST、扫描导入及版权/来源/链接线索；另核读本地 dora 两个文件、参考前端调用脚本、启动脚本和依赖清单。核心来源如下：

| 范围 | 可确认的依据 | 本版处理 |
|---|---|---|
| 转录/排谱/分轨入口 | 可见代码通过 Basic Pitch、librosa、music21、Verovio、Demucs 等公开 API 调用外部库；原始交接说明称中间层自行编写，维护者确认个人项目来源 | 对维护者有权授权的项目工作明确 AGPL；保留第三方依赖和数据例外 |
| 16kHz / 96 带前端 | 本地留存的 Essentia TensorflowInputMusiCNN、TriangularBands、Windowing、Slaney 参考源码头为 AGPL-3.0-or-later；官方公开源码核对一致 | 保留 UPF 版权、AGPL、无担保和静音/尾帧差异说明；没有将前端改成宽松许可 |
| Krumhansl / Temperley 模板 | 数值可在 Essentia Key 对照；Krumhansl 也与 music21 9.9.2 的公开模板相符。music21 的 TemperleyKostkaPayne 是另一组数值，未把它误写成当前 TP 模板的直接来源 | 引用对应算法及上游实现，保留 AGPL / BSD 通知，不宣称自研模型或证明了历史复制路径 |
| _vendor/dora | 上游 MIT；本地 ANSI/print/no-op 形式与上游 colorize/logger/迭代进度形式不同。目录名不能单独证明复制整个上游 | 明确本地最小接口替身，保留上游 MIT 通知；不声称上游作者创作本地代码，也不作全部历史来源保证 |
| tools/reference_frontend.cjs | 项目编写的调用脚本，加载外部 Essentia.js 做验证；源码包没有官方 WASM/JS 运行包 | 项目脚本 AGPL，官方参考包独立条款；fixture 仅合成输入和参考值 |
| YAMNet / Rockchip | Google 模型与 Rockchip ONNX 转换来源、Apache 通知已保留；门控数值处理封装在 ONNX 内，项目调用 ORT | 明确转换件提供者，不把其 Apache 许可扩展到 MTG 模型 |
| 五份 MTG 模型 JSON | 均无独立 license 字段；本地 manifest 的 license 来自官方模型概览 | 修正文档、模块说明和下载提示；原 JSON、模型清单及原许可字节保留 |
| 主要运行依赖 | 锁定的 57 个版本均在已验收环境找到，元数据版本一致；记录许可字段、分类和已找到的许可证文件摘要 | 建立 DEPENDENCY_LICENSES.json，区分代码、模型、数据和原生组件；不打包依赖 |

选取已安装官方 Basic Pitch inference.py / note_creation.py、librosa feature/spectral.py、music21 analysis/discrete.py 四个源码文件，对其中 79 个至少含 30 个 AST 节点的函数作精确 AST 对照（去除文档字符串），与项目函数未出现完整 AST 相同项。这个小范围检查会漏掉改名、修改或其他来源，**不能作为没有复制代码的证明**。具体摘要、文件和方法在 SOURCE_AUDIT.json。

## 修正与新增的许可边界

- BY-NC-SA 声明依据是官方模型概览。五份官方 JSON 不提供独立许可字段，我们的 manifest 不授予模型权利。官方原 LICENSE 中的 ND 正文冲突继续明示。
- Verovio 6.3.0 包内 License-Expression 是 LGPL-3.0-only。
- imageio-ffmpeg 包装器是 BSD-2-Clause；本次实际运行 ffmpeg -L 显示 GPL v3 or later，并有 --enable-gpl / --enable-version3 / --enable-static 标志。这里不再把包装器的 BSD 当作二进制许可。
- music21 的 BSD 声明针对代码，其 corpus / Scala 文件另有条款；本项目不附带或调用它们作为测试数据。
- Basic Pitch 元数据未填写 License / License-Expression，不等于没有许可：包内 LICENSE 和 NOTICE 存在，Apache-2.0 及原通知已保留。
- pretty_midi 0.2.11 元数据声明 MIT，但 RECORD 列出的一份 site-packages 根 LICENSE.txt 不存在；已核对官方仓库 MIT 文本。这里不宣称该 wheel 的通知完整，且当前源码包不分发该 wheel。

## 本次改动的功能影响与证据

24 份 Python 脚本中，21 份字节不变；另两份只更正模块文档字符串，下载器只更正 CONFLICT 提示文本。去除文档字符串并排除该提示赋值后，24/24 AST 相同。六份模型的清单、原始元数据、模型许可原文与数值规则不改。

文档字符串仍计入来源指纹，因此两个模块摘要发生变化，POLICY_LOCK.json 与 SOURCE_PROVENANCE.json 已同步。FRONTEND_VALIDATION.json 保留原验证快照及其旧前端摘要，不冒充本轮重新执行官方参考引擎；当前合成前端和完整本地回归结果另见 LICENSE_REVIEW_ACCEPTANCE.md。旧报告继续用旧源码副本查询。

## 未证明的事项与不联系路线

这不是全部互联网代码相似性搜索，也没有逐项审计 57 个依赖内部捆绑的所有代码、专利、训练数据、字体、模型权重及全部 AI 工具服务条款。没有新的真人贡献者确认待办，不保证未知片段绝不存在。

默认不联系权利人。以后若出现确切未知来源，优先查本地历史与公开许可；确实没有许可且不愿联系时，移除或依据功能需求独立重写。商业化仍使用 NC 模型、公开改编权重或制作完整离线包，需要改变方案或另行取得适用权利，不能由本文件预先批准。

## 主要原始来源

- [Essentia TensorflowInputMusiCNN](https://github.com/MTG/essentia/blob/master/src/algorithms/spectral/tensorflowinputmusicnn.cpp)、[TriangularBands](https://github.com/MTG/essentia/blob/master/src/algorithms/spectral/triangularbands.cpp)、[Key](https://github.com/MTG/essentia/blob/master/src/algorithms/tonal/key.cpp)。
- [dora log.py](https://github.com/facebookresearch/dora/blob/main/dora/log.py)、[MIT LICENSE](https://github.com/facebookresearch/dora/blob/main/LICENSE)。
- [music21 v9.9.2 code license](https://github.com/cuthbertLab/music21/blob/v9.9.2/music21/license.txt)、[Basic Pitch v0.4.0](https://github.com/spotify/basic-pitch/tree/v0.4.0)、[Demucs v4.0.1 license](https://github.com/facebookresearch/demucs/blob/v4.0.1/LICENSE)。
- [MTG 模型概览](https://essentia.upf.edu/models.html)、[模型原 LICENSE](https://essentia.upf.edu/models/LICENSE)、[BY-NC-SA 条文](https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en)、[BY-NC-ND 条文](https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode.en)。

公开网页通过浏览工具核对；本地原始模型许可的字节依据是已保留的来源快照。当前子进程联网受限，未将失败的重下载记录当作成功在线取证。
