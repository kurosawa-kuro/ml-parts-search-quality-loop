"""実サービスへ接続するテストの置き場（既定の `make test` から除外される）。

`docs/07_test_strategy.md`「mockだけでadapterが動くとは扱わない。選定した検索engine
のローカル実体で結合テストを行う」に対応する枠。T3（Vector Baseline 検索）の
実 Qdrant テストはここへ足す。

**marker が無いと既定実行に混ざり、サービス不在で赤くなる**か、逆に
skip を「通った」と誤読させる。`-m integration` で明示的に呼ぶ。
"""

from __future__ import annotations

import socket

import pytest

from parts_search.config.loader import STAGES

QDRANT_HOST, QDRANT_PORT = "127.0.0.1", 6333


def qdrant_listening() -> bool:
    try:
        with socket.create_connection((QDRANT_HOST, QDRANT_PORT), timeout=1):
            return True
    except OSError:
        return False


@pytest.mark.integration
def test_retrieval_stage_is_not_implemented_yet():
    """T3 未実装であることを明示する。

    **実装済みのように skip しない。** ここが実際の検索テストへ置き換わるまで、
    このテストは「未実装」を理由に失敗する。skip にすると
    `-m integration` が緑に見えて、実結合が検証済みだと誤読される。
    """
    assert "retrieval" in STAGES
    pytest.fail("T3 未実装: 実 Qdrant に対する検索結合テストはまだ存在しない")


@pytest.mark.integration
def test_local_qdrant_is_reachable():
    """結合テストの前提。Qdrant が起動していなければ skip する（前提の欠如は skip でよい）。"""
    if not qdrant_listening():
        pytest.skip(f"ローカル Qdrant ({QDRANT_HOST}:{QDRANT_PORT}) が起動していない")
    assert qdrant_listening()
