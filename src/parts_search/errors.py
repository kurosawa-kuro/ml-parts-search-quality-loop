"""Public errors must never interpolate configuration or secret values."""

from __future__ import annotations

import errno as _errno
import os

# docs/06_error_policy.md の分類。ログ・CLI 出力へそのまま載せる。
ERROR_CODES = frozenset(
    {
        "INVALID_INPUT",
        "INCOMPATIBLE_ARTIFACT",
        "DATA_LEAKAGE",
        "INCOMPLETE_EVALUATION",
        "DEPENDENCY_UNAVAILABLE",
        "RETRIEVAL_TRANSIENT",
        "EVENT_CONFLICT",
        "EVENT_UNMATCHED",
        "ARTIFACT_IO",
        "QUALITY_REGRESSION",
        "RELEASE_SMOKE_FAILED",
    }
)


class FoundationError(Exception):
    """Invalid input or failed foundation operation.

    `code` は `docs/06_error_policy.md` の分類。**別種の失敗を同じ文言へ丸めない** —
    容量不足と入力不正が同じ文字列で返ると、運用側で切り分けができない。
    既定は `INVALID_INPUT`（呼び出し側の入力が誤っている）。
    """

    def __init__(self, message: str, *, code: str = "INVALID_INPUT") -> None:
        if code not in ERROR_CODES:
            raise ValueError("Unknown error code")
        super().__init__(message)
        self.code = code


def io_error(message: str, error: OSError) -> FoundationError:
    """OSError を errno 付きで公開する。

    載せるのは errno 名と `os.strerror` だけ。パス・設定値は載せない
    （原因の識別に必要なのは errno であって、場所ではない）。
    """
    name = _errno.errorcode.get(error.errno, "EUNKNOWN")
    detail = os.strerror(error.errno) if error.errno else "unknown I/O failure"
    return FoundationError(f"{message} ({name}: {detail})", code="ARTIFACT_IO")
