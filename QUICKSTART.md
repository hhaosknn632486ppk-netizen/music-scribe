# 从 GitHub 下载到让 AI 助手分析音乐

这条路线面向 **Windows x64、能执行本地命令的 AI 助手**。先跑风格、类型、情感候选的轻量版，不需要大模型 API 密钥。音频分析在本地进行；本工具不会自动接通聊天网页或注册 MCP 服务。

## 1. 下载源码，准备解释器

在 [GitHub](https://github.com/hhaosknn632486ppk-netizen/music-scribe) 点击 **Code → Download ZIP**，解压后在 `music-scribe-main` 文件夹打开 PowerShell。确认当前目录有 `README.md` 和 `music_scribe.py`。已装 Git 的人也可以：

```powershell
git clone https://github.com/hhaosknn632486ppk-netizen/music-scribe.git
cd music-scribe
```

下面命令都在项目根目录运行。推荐用 [uv](https://docs.astral.sh/uv/getting-started/installation/) 管理 Python；未安装时可以使用官方提供的 WinGet 方式：

```powershell
winget install --id astral-sh.uv -e
```

安装后重新打开 PowerShell 并回到项目目录。没有 WinGet 时，按上面 uv 官方页面选择其他安装方式。已有 64 位 Python 3.12 的人可用 `py -3.12 -m venv .venv`，然后跳到下一步。

```powershell
uv venv --python 3.12 --seed .venv
if ($LASTEXITCODE -ne 0) { throw '虚拟环境创建失败，先查看上方报错' }
```

轻量语义版已在独立 Windows x64 / Python 3.12.13 环境验证。完整转录排谱仍使用单独的 3.10 兼容环境，见 [INSTALL.md](INSTALL.md)。Python 3.10 已于 2026-10-01 结束上游维护，不作为轻量版新用户的默认路线。

## 2. 安装轻量依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-semantics.txt
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe doctor.py --mode semantics
```

doctor 输出应有 `tested_target_matches: true`，各项 `matches: true`，退出码 0。不需要激活环境或修改 PowerShell 执行策略。不要将这些命令换成来源不确定的系统 python。

此路线不安装 TensorFlow、torch、Basic Pitch、librosa、music21 或 Verovio，不能做音符转录和排谱。首次安装要联网下载依赖，体积大于源码 ZIP。

## 3. 下载并校验模型

先读 [README 的许可说明](README.md#许可证与模型使用限制)：五份 MTG 模型有非商业条件和未解决的 SA/ND 冲突；下载不增加授权。数据放到源码目录之外：

```powershell
$Data = Join-Path (Split-Path -Parent (Get-Location).Path) 'music-scribe-data'
$Models = Join-Path $Data 'models'
$Audio = Join-Path $Data 'audio'
$Results = Join-Path $Data 'results'

.\.venv\Scripts\python.exe download_models.py --list
.\.venv\Scripts\python.exe download_models.py --models-dir "$Models"
# 阅读提示后在终端输入 yes；明确读过说明的自动化才可加 --yes。
if ($LASTEXITCODE -ne 0) { throw '模型下载未完成，请先解决报错' }
.\.venv\Scripts\python.exe download_models.py --check --models-dir "$Models"
if ($LASTEXITCODE -ne 0) { throw '模型校验未通过' }
```

六份权重合计 **40,640,925 字节，约 40.6 MB**。每个模型的 weights 和 metadata 都应为 true。只下载 `--only gate` 无法运行完整语义；当前入口需要全部六份。

这些 PowerShell 变量只在当前终端有效。重新打开终端时重新定义，或在命令中使用实际绝对路径。推理不会静默下载模型。

## 4. 完整运行音乐与讲话示例

源码没有附带音频。下面的 fetch 是显式联网动作，下载音乐、讲话和鲸声的公开样本；本演示使用音乐和讲话两份。来源与署名见 [samples/README.md](samples/README.md)。

```powershell
.\.venv\Scripts\python.exe fetch_test_samples.py -o "$Audio"
if ($LASTEXITCODE -ne 0) { throw '示例音频下载失败' }
.\.venv\Scripts\python.exe examples\run_demo.py --audio-dir "$Audio" --models-dir "$Models" --output-root "$Results"
if ($LASTEXITCODE -ne 0) { throw '演示未完成，请查看报错' }
```

成功时输出 `status: completed` 和 `demo_dir`。每次建立新目录，里面有：

- `DEMO_RESULT.json`：两份样本的状态与文件位置。
- `brahms.tool.json` / `libri1.tool.json`：可让助手读取的 JSON 返回值。
- `brahms.query.json` / `libri1.query.json`：各样本开头 0–8 秒的局部证据。
- 各分析子目录中的 `semantics.html` 可用浏览器打开，`summary.json` 是简短结果。
- `ASSISTANT_PROMPT.txt`：可复制给助手的调用与解释规则。

本次实测音乐为 music，讲话为 non_music；音乐语义状态为 ambiguous。**不以必须输出确定细风格作为跑通条件**。这两份已使用过的样本是执行演示，不是新的准确率测试集。

### 可选：同一示例加上转录排谱

先按 INSTALL.md 建好完整兼容环境。复用上面的 $Audio、$Models、$Results：

```powershell
.\.venv-core\Scripts\python.exe examples\run_demo.py --with-score --audio-dir "$Audio" --models-dir "$Models" --output-root "$Results"
```

此选项额外取公开音乐的前 12 秒，在结果目录生成本地 WAV，再生成并验证 MusicXML、SVG、MIDI 与语义证据，位置在 DEMO_RESULT.json 的 score_example。不会把该音频加入源码。

短片段示例通过一致性验证；1.3.1 也修复了同一公开音乐完整输入文件的跨小节延音问题，并用另外 3 首音乐回归，见 TIE_FIX_ACCEPTANCE.md。不能由“生成了谱面”推断整首转录可靠；该选项校验失败会返回 partial / 退出码 3。

## 5. 接给你的 AI 助手

把 [examples/assistant_prompt.txt](examples/assistant_prompt.txt) 内容复制给能运行本地命令的助手，再提供项目目录、虚拟环境 Python、输入音频、模型与结果目录的绝对路径。可以这样写，替换示例路径：

```text
请按 music_scribe 的 examples/assistant_prompt.txt 分析音频。
项目：D:\Tools\music-scribe
Python：D:\Tools\music-scribe\.venv\Scripts\python.exe
音频：D:\Audio\我的音乐.wav
模型：D:\Tools\music-scribe-data\models
结果：D:\Tools\music-scribe-data\results
先用 task=semantics，读取 JSON 并解释候选和限制。
我追问某段时，用返回的 query_report 查询，不用整曲风格猜局部。
```

对应实际命令：

```powershell
.\.venv\Scripts\python.exe examples\llm_tool.py analyze --audio 'D:\Audio\我的音乐.wav' --task semantics --models-dir "$Models" --output-root "$Results"
```

标准输出是一份 JSON。顶层 status=completed 只表示执行完成；声音判断在 summary.status / summary.music_presence。日志保存在返回的 output_dir。

查询局部，用返回的 query_report 原样替换下面路径：

```powershell
.\.venv\Scripts\python.exe examples\llm_tool.py query --report 'D:\实际结果目录\semantics.json' --start 0 --end 8
```

字段和失败处理见 [LLM_INTEGRATION.md](LLM_INTEGRATION.md)。普通聊天网页没有本地执行能力时，需要你先在终端运行，再粘贴生成的 JSON；提示词不会自动赋予网页访问电脑文件的能力。若助手使用云端大模型，其读取的 JSON 文本可能发送给服务商；本工具本身不上传音频或调用云端 API。

## 常见卡点

| 现象 | 处理 |
|---|---|
| 找不到 uv / py | 先完成解释器安装，重新开终端；不要假设电脑已有 Python 3.10 |
| unavailable / 退出码 4 | 读 reason；用同一 Python 跑 doctor，用同一模型目录跑 --check，不让大模型猜风格 |
| not_music / uncertain_input / insufficient_evidence | 是有效分析状态，不是安装失败，也不支持补造音乐结论 |
| 权重摘要或大小不符 | 先核查，再显式 --repair；不改 manifest 来迁就坏文件 |
| 输出目录非空 | 包装器会建新子目录；直接调原 CLI 时换新的 -o |
| 想输出 MusicXML/SVG/MIDI | 按 INSTALL.md 使用独立完整环境，再选 task=score 或 all |
| 旧证据指纹不匹配 | 用生成它的源码版本，或用当前版本重跑；不要删校验 |
