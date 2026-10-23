# 安装、模型及已测范围

第一次使用请从 [QUICKSTART.md](QUICKSTART.md) 开始。命令均在项目根目录运行，无需激活环境。

| 路线 | 能力 | 已测平台 | 依赖 |
|---|---|---|---|
| 推荐轻量语义 | 音乐门控、风格/类型/情感候选、局部证据查询 | Windows x64，Python 3.12.13；既有 3.10.22 也保留验证 | requirements-semantics.txt |
| 完整兼容路线 | 转录、调性/BPM/和弦、MusicXML/SVG/MIDI，可加同一语义模型 | Windows x64，Python 3.10.22；修复版另新建 3.10.20 环境复测；3.12 完整转录未验收 | requirements-core.txt |
| 可选分轨 | Demucs / torch | 本轮未重新验收 GPU、权重或新环境 | requirements-separation.txt |

**Python 3.10 已于 2026-10-01 结束上游维护。** 完整路线是当前依赖约束下的旧环境重现方式，不是长期支持承诺。[Python 官方说明](https://www.python.org/downloads/release/python-31011/)。本次没有升级 Basic Pitch、替换模型或安装重量级替代后端来扩展完整支持版本。

## 轻量语义

uv 安装见 [官方页面](https://docs.astral.sh/uv/getting-started/installation/)。已有 64 位 Python 3.12 时也可用 venv。

```powershell
uv venv --python 3.12 --seed .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-semantics.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe doctor.py --mode semantics
```

不要求 py 已注册 Python，也不安装 Basic Pitch、TensorFlow、torch、librosa、music21 或 Verovio。首次获取 Python、依赖及模型需要联网；不提供完全离线安装介质。

## 完整兼容路线：单独环境

不要将完整依赖混装进 Python 3.12 语义环境。用单独目录，模型可复用外部同一份：

```powershell
uv venv --python 3.10 --seed .venv-core
.\.venv-core\Scripts\python.exe -m pip install -r requirements-core.txt
.\.venv-core\Scripts\python.exe -m pip check
.\.venv-core\Scripts\python.exe doctor.py --mode core
```

已有 64 位 3.10 可用 `py -3.10 -m venv .venv-core`，或 `& '实际Python路径' -m venv .venv-core` 替代第一条。未装该版本时 py -3.10 不会自行成功。uv 使用其提供的 Python 构建；本轮修复另用 uv 提供的 3.10.20 新建完整环境，原同环境对照为 3.10.22，不声称验证了所有发行来源。

Basic Pitch 0.4.0 的依赖随平台与 Python 标记变化：Windows Python<3.11 选择 ONNX Runtime，其他组合可能引入 TensorFlow、TFLite 或 CoreML。不要在 3.12 装 core 并期待保持同样轻量。原完整环境的解析记录是 requirements-lock-windows-py310.txt，现补充 setuptools 兼容约束；不要套到 3.12。

只生成谱面，无需六份语义权重：

```powershell
.\.venv-core\Scripts\python.exe examples\llm_tool.py analyze --audio 'D:\Audio\song.wav' --output-root 'D:\Results' --task score
```

联合语义则使用 `--task all --models-dir 'D:\MusicModels\music_scribe'`。MusicXML/SVG/MIDI 实际路径从返回的 artifacts 读取。谱面仍可能有音符、节奏、声部错误。

## 模型下载及校验

需要现成谱面演示时，先按 QUICKSTART.md 下载公开样本，再用完整环境运行 `examples\run_demo.py --with-score`。它只对音乐前 12 秒作额外排谱及验证，不把全长复杂复调的生成成功当成通过校验。

先读 README 的非商业限制与未决冲突。以下以语义环境为例：

```powershell
.\.venv\Scripts\python.exe download_models.py --list
.\.venv\Scripts\python.exe download_models.py --models-dir 'D:\MusicModels\music_scribe'
# 阅读提示后输入 yes，明确读过的自动化才用 --yes
.\.venv\Scripts\python.exe download_models.py --check --models-dir 'D:\MusicModels\music_scribe'
```

六份权重合计 40,640,925 字节，清单见 MODEL_LICENSES.md。下载器放置配对元数据并校验，坏文件默认保留；确认后显式 --repair。`--only gate` 不是独立的完整语义模式。

分析时传 --models-dir，也可设置 MUSIC_SCRIBE_MODELS，命令行优先；终端变量不自动跨会话保存。验证输出也传同一目录：

```powershell
.\.venv\Scripts\python.exe verify_semantics.py 'D:\Results\某次分析目录' --models-dir 'D:\MusicModels\music_scribe'
```

doctor 检查环境，download_models --check 检查模型，verify_semantics 检查输出一致性；都不证明音乐判断准确。

## 分轨、拖放和平台边界

可选 --separate 需要匹配的 torch / torchaudio、Demucs 和已缓存 htdemucs 权重。先按 [PyTorch 官方页](https://pytorch.org/get-started/locally/)选择环境，再安装 requirements-separation.txt。无已缓存权重时明确失败或降级，不自动下载；本轮未验收 GPU。

拖放脚本默认 .venv\Scripts\python.exe。如果这里是轻量语义环境，转录脚本不会因此获得完整依赖。需要完整拖放时，在同一终端设置 MUSIC_SCRIBE_PYTHON 为 .venv-core\Scripts\python.exe 的绝对路径，再从该终端启动；明确指定解释器的命令最容易核对。

- Linux、macOS、ARM、其他 Python 版本未完成同等验收；示例是 Windows PowerShell 格式。
- SSL/代理问题先查看原错误，不通过关闭证书校验绕过。
- 中文/空格路径保持引号，不要求开发者机器上的固定目录。
- verify_source.py --strict 面向干净源码导出，在源码内建环境、缓存或下载权重前执行；已有本地生成文件时报告额外项是防止误上传的设计。
- 离线机器要预先准备匹配平台的依赖与校验过的模型，并遵循各文件许可。

完整环境显式固定 setuptools==80.9.0，为 Basic Pitch 所依赖 resampy 0.4.2 提供 pkg_resources；仅 pip check 不足以发现这个导入兼容问题，doctor 会核对版本。本版在独立新环境完成 selftest 和真实文件复测，见 TIE_FIX_ACCEPTANCE.md；轻量 requirements-semantics.txt 不增加该依赖。
