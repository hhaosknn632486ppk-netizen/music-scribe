"""The two log helpers Demucs actually calls."""

import sys


def bold(text):
    return f"\033[1m{text}\033[0m"


def fatal(*messages):
    print(*messages, file=sys.stderr)
    raise SystemExit(1)


class LogProgress:
    """Demucs uses this only in evaluate/solver paths; keep a no-op compatible form."""

    def __init__(self, messages, total=None, **kwargs):
        self.messages = messages
        self.total = total

    def __call__(self, iterator):
        return iterator

    def update(self, *args, **kwargs):
        pass

    def close(self):
        pass
