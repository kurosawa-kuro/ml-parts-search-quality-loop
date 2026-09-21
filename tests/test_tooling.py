"""テスト基盤そのものの検査。

marker で分離した「つもり」を検証する。設定を書いただけでは
実接続テストが既定実行から外れている保証にならない。

またパッケージレイアウトの退行（`.gitignore` がソースを飲む、
参照が旧名のまま残る）を検出する。2026-09-22 に実害があった。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *argv], capture_output=True, text=True, timeout=120, cwd=REPO
    )


# --- marker 分離が実際に効いているか ---


def test_integration_tests_are_excluded_by_default():
    """既定実行に実接続テストが混ざらない。混ざると services 不在で赤くなる。"""
    completed = run("-m", "pytest", "--collect-only", "-q")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "test_qdrant_integration" not in completed.stdout


def test_integration_tests_exist_and_are_selectable():
    """除外しているだけで、存在しない・呼べないのでは意味がない。"""
    completed = run("-m", "pytest", "--collect-only", "-q", "-m", "integration")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "test_qdrant_integration" in completed.stdout


def test_unknown_marker_is_rejected():
    """`--strict-markers` が効いていれば、綴り違いの marker は静かに無視されない。"""
    completed = run("-m", "pytest", "--collect-only", "-q", "-m", "integraton")
    assert completed.returncode != 0 or "no tests ran" in completed.stdout.lower()


# --- レイアウトの退行検出 ---


def test_no_source_file_is_git_ignored():
    """`.gitignore` の非アンカーパターンがソースを飲む退行を防ぐ。

    2026-09-22: 素の `artifacts/` が `src/parts_search/artifacts/` にも当たり、
    run 公開・検証の中核が新規 clone から欠落していた。
    """
    sources = sorted(str(p.relative_to(REPO)) for p in (REPO / "src").rglob("*.py"))
    assert sources, "src 配下に Python ファイルが無い"
    completed = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        input="\n".join(sources),
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO,
    )
    assert completed.stdout.strip() == "", f"ignore されているソース:\n{completed.stdout}"


def test_every_source_file_is_tracked_by_git():
    """新規 clone で import できることの担保。未追跡のままだと欠落に気付けない。"""
    tracked = subprocess.run(
        ["git", "ls-files", "src"], capture_output=True, text=True, timeout=60, cwd=REPO
    ).stdout.split()
    on_disk = {str(p.relative_to(REPO)) for p in (REPO / "src").rglob("*.py")}
    missing = sorted(on_disk - set(tracked))
    assert not missing, f"git に入っていないソース: {missing}"


def test_no_stale_package_name_remains():
    """改名の取り残しを検出する。import 時ではなく静的に落とす。"""
    stale = []
    for pattern in ("*.py", "*.toml", "*.md"):
        for path in list(REPO.glob(pattern)) + list((REPO / "src").rglob(pattern)):
            if "parts_search_quality_loop" in path.read_text(encoding="utf-8"):
                stale.append(str(path.relative_to(REPO)))
    assert not stale, f"旧パッケージ名が残っている: {stale}"
