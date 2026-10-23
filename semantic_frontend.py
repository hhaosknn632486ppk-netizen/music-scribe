"""16-kHz MusiCNN/EffNet frontend, independently evaluated against Essentia.js.

SPDX-License-Identifier: AGPL-3.0-or-later
Parameter definitions follow MTG Essentia TensorflowInputMusiCNN and
TriangularBands. See LICENSE and FRONTEND_VALIDATION.json for scope.
Essentia algorithms: Copyright (C) 2006-2021 Music Technology Group -
Universitat Pompeu Fabra. Distributed without warranty under AGPL v3 or later.
No Essentia/Node/WASM dependency at runtime.
"""
from functools import lru_cache
import numpy as np
from scipy.fft import rfft

FRONTEND_VERSION = 'musicnn-slaney-f32/1'
SAMPLE_RATE = 16000
FRAME_SIZE = 512
HOP_SIZE = 256
MEL_BANDS = 96


@lru_cache(maxsize=1)
def mel_filters():
    f32 = np.float32
    slope = f32(3 / 200)
    log_step = f32(np.log(6.4) / 27)
    high_mel = f32(f32(1000 * slope) + f32(np.log(f32(8))) / log_step)
    step = f32(high_mel / f32(MEL_BANDS + 1))
    edges = []
    mel = f32(0)
    for _ in range(MEL_BANDS + 2):
        edges.append(f32(mel / slope) if mel < f32(15) else
                     f32(f32(1000) * np.exp(f32(f32(mel - f32(15)) * log_step))))
        mel = f32(mel + step)
    edges = np.asarray(edges, dtype=np.float32)
    frequencies = np.arange(FRAME_SIZE // 2 + 1, dtype=np.float32) * f32(SAMPLE_RATE / FRAME_SIZE)
    filters = np.zeros((MEL_BANDS, len(frequencies)), dtype=np.float32)
    for band in range(MEL_BANDS):
        left, middle, right = edges[band:band + 3]
        rising = (frequencies - left) / f32(middle - left)
        falling = (right - frequencies) / f32(right - middle)
        filters[band] = np.maximum(f32(0), np.minimum(rising, falling)) / f32((right - left) / f32(2))
    return filters


def frame_features(frames):
    frames = np.asarray(frames, dtype=np.float32)
    if frames.ndim != 2 or frames.shape[1] != FRAME_SIZE or not np.isfinite(frames).all():
        raise ValueError('Expected finite float32 frames with shape [N,512]')
    window = np.hanning(FRAME_SIZE).astype(np.float32)
    windowed = np.roll(frames * window, -(FRAME_SIZE // 2), axis=1)
    spectrum = np.abs(rfft(windowed, axis=1, workers=1)).astype(np.float32)
    power = spectrum * spectrum
    # einsum avoids a large BLAS thread pool for these small fixed matrices.
    bands = np.einsum('nf,mf->nm', power, mel_filters(), optimize=False)
    return np.log10(np.float32(1) + np.float32(10000) * bands).astype(np.float32)


def audio_frames(audio):
    """Zero-centered frames, hop 256; tail is zero padded, silent frames kept.

    Deterministic silence handling is explicit; no random noise is added.
    """
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
        raise ValueError('Expected nonempty finite mono audio at 16000 Hz')
    # Essentia FrameCutter(startFromZero=False): one final overlapping frame.
    count = int(np.ceil(len(audio) / HOP_SIZE)) + 1
    padded = np.pad(audio, (FRAME_SIZE // 2, FRAME_SIZE))
    frames = np.lib.stride_tricks.sliding_window_view(padded, FRAME_SIZE)[::HOP_SIZE][:count]
    return frames


def audio_features(audio, block_frames=1024):
    frames = audio_frames(audio)
    blocks = [frame_features(frames[i:i + block_frames]) for i in range(0, len(frames), block_frames)]
    return np.concatenate(blocks)


def patches(features, size, hop=62):
    """Every frame covered once or more; tail zero-padding recorded explicitly.

    Patch centers use real supported frame positions, not padded positions.
    """
    if len(features) < size:
        starts = [0]
    else:
        starts = list(range(0, len(features) - size + 1, hop))
        if starts[-1] + size < len(features):
            starts.append(len(features) - size)
    return starts
