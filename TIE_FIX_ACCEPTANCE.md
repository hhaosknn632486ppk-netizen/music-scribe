> 历史记录：本页是1.3.1延音修复验收。当前1.3.2排版优化及其效果/限制见 [LAYOUT_ACCEPTANCE.md](LAYOUT_ACCEPTANCE.md)。

# 长曲延音连线修复与真实样本验收

日期：2026-10-23。转谱版本 1.3.1，源码变体 github-source-3；对照公开旧提交 afca7e5f7f1997e9e2bb7688cb17fa97f783925b。独立副本开发，原公开源码、本地完整版和历史版本保留。

## 问题与改动

旧公开 Brahms 样本完整文件（45.844875 秒）在第 8 小节起点报 `Unmatched or noncontiguous tie stop: (0, '2', '0', 60), onset=28`。这里是同音延长的 tie，不是乐句 slur。

music21 makeMeasures 将声部分配为从 0 开始的编号，makeTies 会展开只剩一个声部的小节。PartStaff 合并导出发现上谱表缺少正声部编号时，会只在当前小节给下谱表的编号加 1，跨小节延音两端因此可能不一致。

完整模式在音符上保留原始时值通道编号；记谱和时值拆分后，恢复明确的正整数声部编号，两个谱表互不重复，为空小节/声部间隙写出休止符，再序列化已整理的记谱。检测音符、速度、量化、模型和语义规则不改；简化模式沿用原导出路径。

**verify_musicxml.py、verify_output.py 和 verify_semantics.py 均与旧提交逐字节相同。** 没有删除校验、容忍断开的连线或按音高跨声部拼接。新增负例仍拒绝错误声部、错误谱表、时间间隙和缺少终点。

Python 调用者应使用 `write_score_musicxml(build_score(...), path)`；不要自行对完整模式结果重新执行默认 `score.write(...)`，否则会再次进入第三方的声部整理。CLI 已调用正确入口。

## 完整文件对比

Windows x64 / CPython 3.10.22 / CPU；两版同一环境、同一模型、每个文件各执行一次完整转录、排谱和语义分析。时间包含进程启动及分析，不是排谱单步骤计时；安装、下载和独立校验耗时不在其中。每组只有一次顺序测量，不能视为性能改善或退化的统计结论。

| 输入 | 秒数 | 检测音符 | 旧版谱面校验 → 新版 | 新版延音续接段 | 耗时旧→新（秒） | 内存旧→新（MiB） |
|---|---:|---:|---|---:|---:|---:|
| Brahms / Hungarian Dance #5 公共样本全长 | 45.84 | 537 | 失败 → 通过 | 60 | 8.798 → 8.861 | 543.0 → 531.1 |
| Admiral Bob / Choice 鼓与贝斯片段 | 25.03 | 97 | 通过 → 通过 | 0 | 6.998 → 7.385 | 514.9 → 517.8 |
| Karissa Hobbs / Let’s Go Fishin’ 样本全长 | 132.99 | 1950 | 通过 → 通过 | 141 | 18.269 → 19.177 | 596.1 → 595.4 |
| Mihai Sorohan / Trumpet loop | 5.33 | 13 | 通过 → 通过 | 3 | 5.503 → 5.374 | 377.3 → 381.9 |
| 既有私人用户分轨重复至 180 秒（派生压力输入） | 180.00 | 2687 | 失败 → 通过 | 431 | 26.328 → 27.206 | 730.8 → 731.2 |

所有 5 组完整谱面：逻辑音符区间与检测事件量化结果逐项相同，缺失/改变 0、额外/改变 0；两版的 events.json 摘要完全一致。四首公开音乐是 4 个独立音乐录音输入，180 秒压力输入不是新增曲目，也不是 Brahms 样本的重复。未将私人音频、其谱面、公开音频或权重提交到仓库。

另测 LibriSpeech 讲话（14.84 秒）和鲸声（64.81 秒）：两版均为 non_music / not_music，未输出音乐风格或情感。全部 7 组的风格、情感和门控决策逐项不变，语义证据验证通过；5 组联合报告的局部查询通过。短小号仍可能被门控保守拒绝，谱面通过不代表语义支持充分。

内存来自实际分析进程内部记录的 lifetime peak working set，在排谱与语义推理后、最终报告序列化前读取，包含整进程此前峰值，排除子进程、测试启动器和磁盘缓存；不是单独模型占用，也不是整机 RAM。

## 回归与完整环境兼容

- 原完整 Python 3.10.22 环境 99/99；Python 3.12.13 轻量环境 44/44；均无失败或跳过。
- 新增 8 项延音测试，包括 24 组固定种子稀疏复调布局、单/多声部切换、空小节、跨多小节、重叠同音、复合时值、非 4/4 拍以及故意破坏连线的负例。原完整模式测试也改为调用实际导出入口。
- 自测额外发现旧版与修复版在 setuptools 84.2.1 环境均因 resampy 0.4.2 导入 pkg_resources 失败。完整 requirements 增加 setuptools==80.9.0，doctor 同步检查；轻量语义依赖不变。
- 另建 uv Python 3.10.20 隔离环境重新安装完整依赖：pip check、doctor、99/99 回归、8 种三和弦调性 + 4 种七和弦调性 + E 小调到 D 大调合成转调自测均通过。
- 新兼容环境另跑完整 Brahms 的助手入口、537 区间校验、语义校验和 0–8 秒查询；再跑 --with-score 完整新手示例，均通过。具体耗时和结果见 JSON。
- 本地浏览器实际渲染并抽查修复后 Brahms 第 1 页 SVG（包括第 7/8 小节）；其余样本确认文件生成和严格区间校验，未逐页做人工排版验收。

## 复现

在完整兼容环境、已有完整六模型目录的前提下执行：

```powershell
.\.venv-core\Scripts\python.exe -m pip install -r requirements-core.txt
.\.venv-core\Scripts\python.exe -m pip check
.\.venv-core\Scripts\python.exe doctor.py --mode core
$env:MUSIC_SCRIBE_MODELS='D:\MusicModels\music_scribe'
.\.venv-core\Scripts\python.exe -m unittest test_correctness test_semantics test_gate test_download_models test_llm_tool test_ties -v
.\.venv-core\Scripts\python.exe selftest.py
.\.venv-core\Scripts\python.exe fetch_test_samples.py -o D:\MusicSamples
$Audio = Get-ChildItem D:\MusicSamples -Filter "Hungarian_Dance*.ogg" | Select-Object -First 1
.\.venv-core\Scripts\python.exe music_scribe.py "$($Audio.FullName)" -o D:\MusicResults\brahms_fixed_01 --mode full --semantics --models-dir "$env:MUSIC_SCRIBE_MODELS"
.\.venv-core\Scripts\python.exe verify_output.py D:\MusicResults\brahms_fixed_01
.\.venv-core\Scripts\python.exe verify_semantics.py D:\MusicResults\brahms_fixed_01 --models-dir "$env:MUSIC_SCRIBE_MODELS"
```

结果目录必须是新的空目录；旧版对照请在保留的旧源码副本或固定旧提交中执行相同命令，使用另外的结果目录。旧报告继续由生成它的源码副本查询和校验，新版不绕过源码指纹检查。

## 样本出处与许可边界

以下是本地既有样本清单及对应来源文本的记录，未重新取得额外授权，也未把来源声明扩大为人工标注真值：

- Brahms - Hungarian Dance #5：https://librosa.org/data/audio/Hungarian_Dance_number_5_-_Allegro_in_F_sharp_minor_%28string_orchestra%29.ogg；SHA256 `919b48aa4cc66a0357d2cd5728664c5ab8f15c4b3469460df4b59470d35d3e49`。原始署名/许可依据保存在 JSON 的 license_and_source。
- Admiral Bob - Choice (drum+bass)：https://librosa.org/data/audio/admiralbob77_-_Choice_-_Drum-bass.ogg；SHA256 `ac644f9645e7c15174e4a4f8561e4d1448d7f6e59ff6b0556b310ebbced879bc`。原始署名/许可依据保存在 JSON 的 license_and_source。
- Karissa Hobbs - Let's Go Fishin'：https://librosa.org/data/audio/Karissa_Hobbs_-_Lets_Go_Fishin.ogg；SHA256 `27b3667c396c1831511aa3c415fcf582b6e8be560cafb844c5b67b76b72c1cb3`。原始署名/许可依据保存在 JSON 的 license_and_source。
- Mihai Sorohan - Trumpet loop：https://librosa.org/data/audio/sorohanro_-_solo-trumpet-06.ogg；SHA256 `8374466fd3951d24509da6e799b132a0db0bdeda69d99c69d989a6888d3d727d`。原始署名/许可依据保存在 JSON 的 license_and_source。
- Ashiel Mystery - A Detective Story, chapter 2, narrated by Garth Comira：https://librosa.org/data/audio/5703-47212-0000.ogg；SHA256 `a284612b46af0535f7e1873758c4387bb8369f6dbbe192ffdec1f171108f98dd`。原始署名/许可依据保存在 JSON 的 license_and_source。
- Glacier Bay 60-second clip humpback whale song November 2020：https://librosa.org/data/audio/glacier-bay-humpback.ogg；SHA256 `64395c617b28b5e31a03032b99b4617bc96b926f3bc5c141862cd13fb79ccd8e`。原始署名/许可依据保存在 JSON 的 license_and_source。

Choice 的原始说明同时出现 BY-NC 3.0 描述和 4.0 链接，本轮未裁定二者关系，也不附带录音或派生谱面。私人 180 秒输入没有公开下载地址，不作为别人可匿名重跑的公开样本。公开用户可自行提供长录音复现，但不能把本轮数字当作对该录音的结果。

## 剩余限制

这次修复的是延音链的文件一致性，不能证明原音识别正确、旋律/配器正确或已经达到人工总谱水平。仍有默认拍号、单一全局速度、十六分音符量化、转录漏音/错音以及机械声部/休止符拥挤；music21 符杠警告仍会出现，未作乐谱美观或每页排版质量保证。

4 首复用音乐样本与 2 个非音乐样本没有独立音符真值，180 秒又是重复派生材料，不代表大量未见长曲。没有新测 GPU、Demucs、Linux/macOS/ARM 或升级完整 Python 支持；Python 3.10 和 pkg_resources 兼容约束仍需后续维护。AGPL、模型非商业条件及 SA/ND 冲突保持原说明。
