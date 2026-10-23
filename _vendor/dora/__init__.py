"""Minimal stand-in for facebookresearch/dora, which Demucs imports at module load.

Demucs only needs ``dora.log.fatal`` and ``dora.log.bold`` on the inference path
(``demucs/pretrained.py``, ``demucs/separate.py``). Installing the real package
drags in omegaconf / submitit / treetable just to print two log lines, so this
shim provides exactly those and nothing else.

Keep it first on sys.path so it shadows any real ``dora`` install.
"""

__version__ = "0.0.0-shim"
