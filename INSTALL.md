# 安装步骤与已测范围

## Windows x64 / CPython 3.10

使用官方64位CPython 3.10，在解压后的源码目录打开PowerShell：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-core.txt
.\.venv\Scripts\python.exe doctor.py --mode core
```

不需要激活环境；使用完整解释器相对路径可避免PowerShell脚本执行策略问题。基础组提供转录、排谱和本地codec回退，不要求另行下载语义权重。依赖安装可能联网下载Python包及其中的Basic Pitch模型/ffmpeg构建；它不是纯源码自带模型，也不是“首次安装完全离线”。

只要语义、不需要转录/排谱时，可以只安装轻量依赖组：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-semantics.txt
.\.venv\Scripts\python.exe doctor.py --mode semantics
.\.venv\Scripts\python.exe download_models.py --models-dir 'D:\MusicModels\music_scribe'
$env:MUSIC_SCRIBE_MODELS='D:\MusicModels\music_scribe'
.\.venv\Scripts\python.exe music_scribe.py 'D:\Audio\clip.wav' -o 'D:\Results\new_semantics' --semantics-only
```

基础组与语义组有共享依赖，安装两者不会创建第二份模型实现。原有六权重及其SHA固定，合计40,640,925字节；下载器不换模型也不重新训练。五份MTG权重有未解决许可文本冲突，先读LICENSE_STATUS.md。模型下载可以手动从清单URL取得，但仍需用`download_models.py --check`核验，并保留对应元数据。

本机测试的完整解析版本见requirements-lock-windows-py310.txt；这是本候选在Windows/Python3.10的重现锁定，其他平台不要机械套用。公开源码不包含环境或包缓存。若要无网机器安装，需要事先按对应平台准备pip wheelhouse及经校验模型，离线转移它们，并遵守各文件许可；本包没有宣称提供这种完整离线安装介质。

## 可选分轨

仅--separate需要额外的torch、torchaudio、Demucs和已缓存htdemucs权重。先按[PyTorch官方安装页](https://pytorch.org/get-started/locally/)选择匹配的CPU/GPU版本，再安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-separation.txt
```

分轨代码保留，默认使用本环境torch；也可用MS_TORCH_PATH指向已有兼容site-packages。源码不附带开发者环境的torchpath.txt。没有已缓存Demucs权重时保持明确失败/既有降级行为，不自动下载；如另行取得权重，需要核查该权重的来源和许可。此源码整理未重新验收GPU、Demucs权重来源或其模型质量，不能把基础安装成功说成分轨新环境已通过。

## Python/平台限制与排错

- 当前完整验收目标为Windows x64、Python3.10；Linux/macOS/ARM和Python3.11+未完成同等验收。
- Basic Pitch 0.4.0的官方依赖使用平台/Python标记：Windows Python<3.11会选ONNX Runtime；其他组合可能安装TensorFlow、TFLite或CoreML。不要以为任意版本都会保持同样轻量。
- doctor.py只检查版本、平台和分组依赖，不代替音频转录或桌面拖放测试。缺依赖或版本不符会明确输出。
- 权重路径支持中文和空格；模型摘要错误先用--check确认，再显式--repair，不手动改manifest来迁就坏文件。
- 如果SSL、代理或模型站点不可达，下载器报错并保留既有文件；不要关闭证书验证。之后可重试显式下载或离线校验。
- 拖放入口找不到解释器时，先检查源码目录`.venv\Scripts\python.exe`，或设置MUSIC_SCRIBE_PYTHON。无参数双击会显示拖放提示，不会自行选择文件。
