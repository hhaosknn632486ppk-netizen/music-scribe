# 第三方来源、通知与分发边界

本文件区分项目实现、参考源码、外部依赖、模型权重与数据。维护者有权授权的项目工作采用 AGPL-3.0-or-later，第三方权利与条件继续保留。具体范围见 LICENSE_SCOPE.md；核对依据和限制见 SOURCE_AUDIT.md。

## 源码参考与接口

**Essentia / MTG-UPF。** Copyright (C) 2006-2021 Music Technology Group - Universitat Pompeu Fabra。已保留前端参考源码头中的 AGPL-3.0-or-later 及无担保声明，全文见根 LICENSE。来源：[TensorflowInputMusiCNN](https://github.com/MTG/essentia/blob/master/src/algorithms/spectral/tensorflowinputmusicnn.cpp)、[TriangularBands](https://github.com/MTG/essentia/blob/master/src/algorithms/spectral/triangularbands.cpp)、[Key 模板](https://github.com/MTG/essentia/blob/master/src/algorithms/tonal/key.cpp)。本地 NumPy/SciPy 前端采用对应参数和数学处理并有记录的静音、尾帧与时间汇总差异；不声称完全等同官方解码器。Essentia.js 0.1.3 仅用于独立验证，不包含其 Node/WASM 运行包。源码参考与数值对照不代表真实识别准确率。

**调性模板。** 项目使用公开 Krumhansl 和 Temperley 模板，相关数值可在上述 Essentia Key 实现核对；Krumhansl 数值也可与 [music21 9.9.2 analysis.discrete](https://github.com/cuthbertLab/music21/blob/v9.9.2/music21/analysis/discrete.py) 对照。项目不是将完整 music21 调性类复制进来。相关算法参考包括 D. Temperley, “What's key for key? The Krumhansl-Schmuckler key-finding algorithm reconsidered”, Music Perception 17(1), 65-100, 1999。保留 music21 的 BSD-3-Clause 通知于 THIRD_PARTY_LICENSES/music21-BSD.txt；不把文献或数值来源冒充项目训练模型。

**dora 接口替身。** _vendor/dora 是早期项目中的本地最小兼容实现；经与上游 log.py 对照，其 bold 使用 ANSI 字符串、fatal 直接输出并退出、LogProgress 为无操作替身，上游实现采用 treetable/logger/迭代进度逻辑。接口名称相同不足以证明完整复制，也不足以证明所有历史来源；本项目不作此类保证。上游 Copyright (c) Facebook, Inc. and its affiliates，MIT，保留完整许可于 THIRD_PARTY_LICENSES/dora-MIT.txt。[上游接口](https://github.com/facebookresearch/dora/blob/main/dora/log.py)、[上游许可](https://github.com/facebookresearch/dora/blob/main/LICENSE)。保留通知不把上游作者认定为本地替身作者。

## 模型与元数据

**YAMNet。** Copyright 2019 The TensorFlow Authors，Apache-2.0；来源 [Google YAMNet](https://github.com/tensorflow/models/tree/master/research/audioset/yamnet)，原通知见 models/LICENSE-YAMNET.txt。波形 ONNX 是 [Rockchip rknn_model_zoo](https://github.com/airockchip/rknn_model_zoo/tree/main/examples/yamnet) 提供的转换件，保留 models/LICENSE-RKNN.txt；不能表述为 Google 直接发布的 ONNX。标签表及由其整理的元数据保留原出处。源码包不含权重。

**五份 MTG/UPF 语义权重。** [官方概览](https://essentia.upf.edu/models.html)声明 CC BY-NC-SA 4.0；五份官方 JSON 中没有单独的 license 字段。作者、引用和推理信息原样保留。models/manifest.json 记录概览声明，不是独立授权。原 LICENSE 含 ND 正文，原样保留在 models/LICENSE.txt；争议范围与本地非商业安排见 LICENSE_STATUS.md。源码包不含权重；YAMNet 的 Apache 许可不改变这些模型的条款。

**Basic Pitch。** Copyright 2022 Spotify AB，官方 0.4.0 Python 包与包内模型由安装源提供，源码候选不复制其推理实现或权重。包内 LICENSE（Apache-2.0）与 NOTICE 完整保留在 THIRD_PARTY_LICENSES/，其中 NOTICE 还列出其自身第三方来源，不将空白 License 元数据误写成没有许可。[官方 v0.4.0](https://github.com/spotify/basic-pitch/tree/v0.4.0)。

## 主要外部运行依赖

以下由用户安装取得，源码包不包含依赖源码、wheel、DLL、字体或可执行文件。核对基于锁定版本的包内元数据与许可文本；全部 57 项观察结果见 DEPENDENCY_LICENSES.json。依赖有公开许可时按条款使用，不以逐个取得作者回信为前置。

| 依赖 / 版本 | 已核对许可与边界 | 官方来源 |
|---|---|---|
| numpy 2.2.6 / scipy 1.15.3 | BSD-3-Clause 主体及其分发附带的其他组件条款；不能以主体许可概括 OpenBLAS 等全部内容 | https://numpy.org/ 、https://scipy.org/ |
| librosa 0.11.0 | ISC | https://github.com/librosa/librosa |
| onnxruntime 1.23.2 | MIT；包内另有 ThirdPartyNotices，未逐项审计其内部组件 | https://github.com/microsoft/onnxruntime |
| soundfile 0.14.0 | Python 包 BSD-3-Clause；libsndfile 等原生组件另有条款 | https://github.com/bastibe/python-soundfile |
| soxr 1.1.0 | LGPL-2.1-or-later；libsoxr、PFFFT 的包内通知另列 | https://github.com/dofuuz/python-soxr |
| imageio-ffmpeg 0.6.0 | 包装代码 BSD-2-Clause；本机实际 ffmpeg 7.1 的 -L 声明 GPL-3.0-or-later，不能统一写成 BSD | https://github.com/imageio/imageio-ffmpeg 、https://ffmpeg.org/legal.html |
| music21 9.9.2 | Python 代码 BSD-3-Clause；corpus / Scala 等数据不由这个声明覆盖，本项目不附带或调用其曲库作为样本 | https://github.com/cuthbertLab/music21 |
| verovio 6.3.0 | 已安装元数据为 LGPL-3.0-only；不能泛写成 or-later；字体及资源另查，本源码包不附字体或谱面 | https://github.com/rism-digital/verovio |
| pretty_midi 0.2.11 / mido 1.3.3 | MIT；pretty_midi 的 RECORD 指向一份本地缺失的 LICENSE.txt，元数据和官方许可支持 MIT，但不声称该 wheel 的通知完整 | https://github.com/craffel/pretty-midi 、https://github.com/mido/mido |
| 可选 demucs 4.0.1 | 官方代码 MIT；本轮未安装或重新审计其模型及整个 torch 栈，权重不随源码包分发 | https://github.com/facebookresearch/demucs/tree/v4.0.1 |
| 可选 torch / torchaudio | 由用户另选兼容版本；其代码、原生组件、CUDA 及模型分别适用各自条款，本轮不作统一许可结论 | https://pytorch.org/ |

## 数据、输出及以后打包的边界

samples/SAMPLES.json 只保留三份公开录音的引用、发布方许可说明及摘要，样本音频不在包内；素材使用方式仍需遵循 samples/README.md 和实际来源条款。tests/fixtures/frontend_fixture.npz 为合成帧和参考输出，不含真实录音。

用户输入、原音乐作品、生成谱面/MIDI 的权利不由软件许可证统一解决。第三方作者没有为本工具或输出背书。当前是源码候选，不能把本轮结论直接用于 exe、离线全模型包、依赖再分发、字体包或已有 Git 历史/Release 附件。

## 1.3.1 完整环境兼容补充

完整依赖固定 setuptools 80.9.0，为 resampy 0.4.2 提供 pkg_resources；安装包元数据/原始许可为 MIT，内嵌第三方组件继续适用各自通知。已安装包的通知文件摘要补入 DEPENDENCY_LICENSES.json；没有把依赖 wheel、vendored 代码或权重复制到本仓库。原 57 项清单保留其当时的核对范围。
