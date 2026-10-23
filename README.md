# music_scribe：本地转录、排谱与可选音乐语义

这是转谱 1.3.3 的独立公开源码版本（github-source-5）。保留音符转录、调性/BPM/和弦、简化/完整MusicXML及SVG谱面、可选Demucs分轨、音乐门控、风格/情绪/人声倾向和连续效价/唤醒分析。没有替换模型、减少语义功能或调整分类规则。

**本版谱面更新：** 减少冗余升降号，按符杠组调整符干并固定延音链弧线侧；五组完整输入页数均未增加。117项完整回归、44项轻量回归通过。改善、局部退步与限制见 [ENGRAVING_ACCEPTANCE.md](ENGRAVING_ACCEPTANCE.md)。

**第一次使用：按 [QUICKSTART.md](QUICKSTART.md) 从安装、下载模型到音乐/讲话示例完整跑一遍。** 给能执行本地命令的 AI 助手使用时，参考 [LLM_INTEGRATION.md](LLM_INTEGRATION.md) 与 [可复制的助手指令](examples/assistant_prompt.txt)。无需大模型 API 密钥；这不是自动注册的 MCP 服务或聊天网页插件。

本源码包不附带语义权重、Python环境、原始录音、用户谱面或私人历史。基本转录所用Basic Pitch模型随其官方Python依赖提供；不属于这里六份可选语义权重。首次安装依赖/显式下载模型需要网络；后续语义推理读取本地文件，不调用云端大模型或下载器。可选分轨仍只使用已缓存Demucs权重。

## 许可证与模型使用限制

| 内容 | 适用范围与条件 |
|---|---|
| 项目代码及原创文档 | **AGPL-3.0-or-later**，见 [LICENSE](LICENSE) 和 [许可范围](LICENSE_SCOPE.md)。AGPL 本身允许商业使用；分发修改版本及提供修改版本的网络交互服务时，应满足对应源码和通知要求。第三方材料保留各自条款。 |
| 五份 MTG 音乐语义模型 | 官方模型概览声明 **CC BY-NC-SA 4.0**，包含非商业条件。本版按原始权重、本地非商业使用安排；不承诺完整模型组合可自由商用。免费提供服务也不自动等于非商业。 |
| MTG 未解决的许可冲突 | 官方原 LICENSE 的标题及正文包含 **NoDerivatives（ND）**，其中链接却指向 BY-NC-SA；五份官方 JSON 没有独立 license 字段。本仓库保留原文及矛盾，**没有替权利人认定 SA 或 ND 哪个有效，也没有取得额外商业授权**。 |
| YAMNet 门控模型 | Google YAMNet 与 Rockchip 转换来源的 Apache-2.0 通知分别保留；其宽松许可不会改变上述五份 MTG 模型的非商业条件。 |

**仓库不包含模型权重或真实音频。** 不随源码分发微调、量化或转换后的 MTG 权重，也不建立权重镜像；需要模型时，由用户阅读许可及冲突提示后显式从原发布源下载到本地。下载器、输入 yes 或传入 --yes 都不会授予额外权利。模型原许可文件保持不变，不能通过移除权重或放置 AGPL 文件推定整套功能获得商业许可。

本地完整版独立保留。仓库中的第三方来源、边界和未决事项分别见 [LICENSE_STATUS.md](LICENSE_STATUS.md)、[MODEL_LICENSES.md](MODEL_LICENSES.md)、[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [SOURCE_AUDIT.md](SOURCE_AUDIT.md)。源码与模型的许可分开标注；“本版按非商业用途使用模型”不会向 AGPL 代码额外添加禁止商用条款。

这是有限范围的来源核对，不保证所有依赖内部组件、训练数据和所有使用情境均已完成权利审计。

## 安装与运行

轻量语义版已验证 Windows x64 / Python 3.12.13；完整转录排谱保留单独的 Python 3.10 兼容环境。3.10 已结束上游维护，不是轻量版的新用户默认选择。先按 [INSTALL.md](INSTALL.md) 选路线，其他 OS/ARM 未完成同等验收。

```powershell
# 在源码目录中；完整兼容环境只做转录/排谱，无需六份语义权重
.\.venv-core\Scripts\python.exe examples\llm_tool.py analyze --audio 'D:\Audio\song.wav' --output-root 'D:\Results' --task score

# 阅读许可和冲突提示，显式下载完整语义权重到独立本地目录
.\.venv\Scripts\python.exe download_models.py --models-dir 'D:\MusicModels\music_scribe'

# 轻量环境只运行本地语义；stdout 为单个 JSON，每次自动创建结果子目录
.\.venv\Scripts\python.exe examples\llm_tool.py analyze --audio 'D:\Audio\song.wav' --output-root 'D:\Results' --task semantics --models-dir 'D:\MusicModels\music_scribe'

# 完整兼容环境联合转录、完整谱面和语义
.\.venv-core\Scripts\python.exe examples\llm_tool.py analyze --audio 'D:\Audio\song.wav' --output-root 'D:\Results' --task all --models-dir 'D:\MusicModels\music_scribe'

# 只读返回的 query_report 路径，按原音频时间查询；不重新推理
.\.venv\Scripts\python.exe examples\llm_tool.py query --report 'D:\Results\run-实际目录\semantics.json' --start 2 --end 8
```

包装器在 output-root 下创建新目录；直接调用原 music_scribe.py 时，-o 目录仍须不存在或为空。拖放入口默认 .venv；要用完整环境排谱，需按 INSTALL.md 指定 MUSIC_SCRIBE_PYTHON。模型可通过 MUSIC_SCRIBE_MODELS 或 --models-dir 设置，命令行优先。

可选公开数据下载/本地评测工具及外部前端复核入口也保留，见[samples/README.md](samples/README.md)。只提供去除私人路径的三份公开样本引用，不附带录音或历史私人数据清单。

## 模型获取和故障行为

下文简写的python均指已创建的`.venv`解释器；未激活环境时，请使用`.\.venv\Scripts\python.exe`替换它。逐模型来源、摘要与许可状态见[MODEL_LICENSES.md](MODEL_LICENSES.md)。

```powershell
python download_models.py --list
python download_models.py --only gate --models-dir 'D:\MusicModels\gate'
python download_models.py --check --models-dir 'D:\MusicModels\music_scribe'
# 只在明确要替换选中的坏文件时使用；新文件校验成功后才原子替换
python download_models.py --repair --models-dir 'D:\MusicModels\music_scribe'
```

下载前逐项显示许可和来源，需输入yes；自动化可显式传--yes，其含义是确认已阅读上述说明，不会消除许可冲突。`--only gate`只取得Apache-2.0的YAMNet及其元数据；它不是新的独立门控分析命令，完整语义仍需全部六份。纯转录根本不需要这些权重。

下载器只接受固定清单中的HTTPS URL，校验精确字节数与SHA256，临时文件验证通过后才原子写入。404、断网、中断和摘要不符会报错并移除本次临时文件；既有坏文件默认保持不动，需显式--repair。推理绝不静默调用下载器，缺失/损坏权重返回unavailable和明确的获取提示；联合分析保留原转录结果及语义失败原因。

## 测试与解释边界

```powershell
# 先使用已经下载且校验通过的完整六模型目录
$env:MUSIC_SCRIBE_MODELS='D:\MusicModels\music_scribe'
.\.venv\Scripts\python.exe -m unittest test_gate test_download_models test_llm_tool -v
# test_semantics 含 librosa 对照，放在完整环境中运行；另含延音与排版回归，共117项
.\.venv-core\Scripts\python.exe -m unittest test_correctness test_semantics test_gate test_download_models test_llm_tool test_ties test_layout test_engraving -v
.\.venv-core\Scripts\python.exe selftest.py
.\.venv-core\Scripts\python.exe verify_output.py 'D:\Results\new_full'
.\.venv-core\Scripts\python.exe verify_layout.py 'D:\Results\new_full\score.musicxml' --check-staff-rests
.\.venv-core\Scripts\python.exe verify_engraving.py 'D:\Results\new_full\score.musicxml'
.\.venv\Scripts\python.exe verify_semantics.py 'D:\Results\new_semantics' --models-dir 'D:\MusicModels\music_scribe'
```

不含权重的核心测试与受控传输测试不访问网络。原始语义测试需要完整本地模型，不会自动下载或悄悄跳过。当前新用户安装和示例验收见 [NEW_USER_ACCEPTANCE.md](NEW_USER_ACCEPTANCE.md)，历史验收见 [ACCEPTANCE.md](ACCEPTANCE.md)；其中公开数值不能当成曲目级识别准确率。

schema继续为music-scribe/1.1和music-semantics/1.1；转谱tool_version为1.3.3，未改动的语义分支仍为1.3.0，源码变体和文件配对另记在SOURCE_PROVENANCE.json、POLICY_LOCK.json及输出指纹。细风格证据不足退回粗类，非音乐或不确定输入拒绝风格/情绪；局部讲话查询不会借用整曲风格。调用规则见[LLM_INTEGRATION.md](LLM_INTEGRATION.md)。

源码整理改变了语义模块指纹；旧1.3的语义报告请继续用原副本query，新副本不绕过代码配对校验。已有HTML仍可静态查看。改动范围见[CHANGES.md](CHANGES.md)。

模型分数未经概率校准，粗类/情绪会误判；弱背景音乐、氛围/噪音音乐和短独奏可能被门控误拒。情绪是听感候选，不证明作者意图。30分钟输入上限、内存解码、近似时间窗口等既有限制保留。曲名、歌手身份、歌词、续写和完整多乐器人工级总谱不在现有能力范围内。

**上一版1.3.1 已修复完整模式跨小节延音的声部编号不一致。** 原失败的 45.84 秒 Brahms 输入完整文件、另外 3 首音乐及 180 秒派生压力输入均通过严格区间校验；完整回归 99/99，轻量 44/44。旧版失败和修复后效果、耗时、内存、样本限制见 [TIE_FIX_ACCEPTANCE.md](TIE_FIX_ACCEPTANCE.md)。completed 仍不等于自动验证通过或转录准确。

此前许可整理的历史修改清单、回归与限制见 [LICENSE_REVIEW_ACCEPTANCE.md](LICENSE_REVIEW_ACCEPTANCE.md)。当时仅修正许可说明、两个模块文档字符串及下载提示；模块摘要因文档字符串变化而改变，旧候选的语义证据继续由旧副本查询，新候选生成的证据按新摘要配对。根 LICENSE、模型原始许可、六模型清单及数值策略未改。

本次 GitHub 源码整理的文件边界与校验方法见 [GITHUB_PUBLICATION.md](GITHUB_PUBLICATION.md)。历史验收文件保留各自日期与当时的发布状态；当前文件完整性以本版本 MANIFEST.json 为准。

此前 github-source-2 增加新手指南、本地 JSON 助手入口、演示和验证器显式模型目录，当时音乐推理代码及权重未改。已重新运行官方前端参考验证并刷新此前因注释改动失配的摘要，详见 NEW_USER_ACCEPTANCE.md。

本版另约束完整环境 setuptools==80.9.0，修复旧 resampy 自测入口缺 pkg_resources 的兼容问题，doctor 会核对。轻量环境不增加依赖。旧谱面报告应由保留的生成版本查询/校验，或使用本版重新分析；静态 HTML 可直接查看。
