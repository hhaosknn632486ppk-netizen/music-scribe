"""分轨（Demucs htdemucs）。作为独立进程运行，主流程只在 --separate 时调用。

torch 为可选依赖，可安装在当前环境，或通过 MS_TORCH_PATH 指定已有兼容环境。
本源码包不携带机器专属 torchpath.txt；若用户自行创建该配置，仍可只读使用。
"""

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_torch():
    """返回 (torch, device字符串)。找不到就抛 RuntimeError，由调用方降级。"""
    try:
        import torch
    except ImportError:
        candidates = [os.environ.get("MS_TORCH_PATH", "")]
        cfg = HERE / "torchpath.txt"
        if cfg.exists():
            candidates.append(cfg.read_text(encoding="utf-8").strip())
        for path in candidates:
            if path and Path(path).is_dir() and path not in sys.path:
                sys.path.append(path)
                try:
                    import torch
                    break
                except ImportError:
                    continue
        else:
            raise RuntimeError(
                "找不到 torch。设置环境变量 MS_TORCH_PATH 指向含 torch 的 site-packages 目录。")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return torch, device


def separate(src: Path, out_dir: Path, model_name="htdemucs", progress=True):
    """把 src 拆成各声部 wav，返回 {stem名: 路径}。"""
    sys.path.insert(0, str(HERE / "_vendor"))      # dora 替身必须在 demucs 之前
    torch, device = _load_torch()

    import numpy as np
    import soundfile as sf
    import librosa
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    def offline_download(*args, **kwargs):
        raise RuntimeError('本副本禁止自动下载 Demucs 权重；请使用已经缓存的模型。')
    torch.hub.download_url_to_file = offline_download
    model = get_model(model_name)
    model.to(device)
    model.eval()

    # 不用 demucs.audio.AudioFile：它靠 ffmpeg 探测/重采样，本机没有 ffmpeg。
    # librosa 走 libsndfile，mp3/m4a/flac 都能直接读。
    data, _ = librosa.load(str(src), sr=model.samplerate, mono=False)
    if data.ndim == 1:
        data = np.stack([data] * model.audio_channels)
    elif data.shape[0] != model.audio_channels:
        data = np.stack([data.mean(0)] * model.audio_channels)
    wav = torch.from_numpy(np.ascontiguousarray(data)).float()
    if wav.shape[1] < model.samplerate:                 # 太短的素材补零，避免卷积报错
        pad = torch.zeros(wav.shape[0], model.samplerate - wav.shape[1])
        wav = torch.cat([wav, pad], dim=1)
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / (ref.std() + 1e-8)

    with torch.no_grad():
        sources = apply_model(model, wav[None], device=device, progress=progress,
                              split=True, overlap=0.25)[0]
    sources = sources * ref.std() + ref.mean()

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, source in zip(model.sources, sources):
        p = out_dir / f"{name}.wav"
        sf.write(str(p), source.cpu().numpy().T, model.samplerate, subtype="PCM_16")
        paths[name] = p
    return paths, {"device": device, "samplerate": model.samplerate,
                   "sources": list(model.sources), "model": model_name}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--model", default="htdemucs")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    paths, info = separate(Path(args.src), Path(args.out), args.model, not args.quiet)
    print(f"[stems] device={info['device']} sr={info['samplerate']} 输出 {len(paths)} 轨", flush=True)
    for name, p in paths.items():
        size = p.stat().st_size / 1024 / 1024
        print(f"  {name:8s} {size:7.1f} MB  {p}", flush=True)


if __name__ == "__main__":
    main()
