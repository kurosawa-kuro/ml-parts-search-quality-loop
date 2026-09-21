"""実行ログの最小設定。設定値や秘密情報をログへ出さない。

`.claude/rules/security.md`: 認証情報・接続文字列をログに出さない。
ここでは **レベルと段階名・件数だけ**を出し、設定の中身は出さない
（設定の記録は成果物側の `config.json` が担う）。
"""

from __future__ import annotations

import logging
import sys

LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}
LOGGER_NAME = "parts_search"


def configure(level: str) -> logging.Logger:
    """設定の logLevel を stdlib logging へ写す。

    stdout は CLI の JSON 出力専用なので、**ログは stderr へ出す**。
    両方を混ぜると `parts-search ... | jq` が壊れる。
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(LEVELS.get(level, logging.INFO))
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
