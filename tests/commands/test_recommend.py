import json
from pathlib import Path
from unittest.mock import patch

import pytest

from codoc.commands.init import run_init
from codoc.commands.recommend import (
    AgentRanker,
    HeuristicRanker,
    RecommendError,
    SpecRecommendation,
    run_recommend,
)
from codoc.config import LlmConfig
from codoc.llm import LlmError
from tests.support.cli import run_cli
from tests.support.fs import write_text
from tests.support.git import git_repository


def _package(
    repo: Path,
    rel: str,
    *,
    files: list[str],
    with_spec: bool = False,
    init: bool = True,
) -> Path:
    pkg = repo / Path(rel)
    pkg.mkdir(parents=True, exist_ok=True)
    if init:
        write_text(pkg / "__init__.py", "")
    for name in files:
        write_text(pkg / name, f"# {name}\n")
    if with_spec:
        write_text(pkg / "codoc.spec.yaml", "docs: []\ncoverage:\n  source: []\n")
    return pkg


class RecommendTests:
    def test_lists_src_packages_without_spec(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", "engine:\n  name: zensical\n")
        _package(git_repo, "src/widgets", files=["a.py", "b.py"])
        _package(git_repo, "src/core", files=["x.py"], with_spec=True)
        result = run_recommend(git_repo)
        scopes = [row.scope_dir.as_posix() for row in result.rows]
        assert scopes == ["src/widgets"]
        assert "without codoc.spec.yaml" in result.rows[0].rationale
        assert "3 .py files" in result.rows[0].rationale
        assert result.ranking == "heuristic"
        index = git_repo / ".codoc" / "index" / "packages.json"
        assert index.is_file()
        payload = json.loads(index.read_text(encoding="utf-8"))
        assert {row["scope_dir"] for row in payload["packages"]} == {
            "src/core",
            "src/widgets",
        }

    def test_includes_nested_package_without_spec(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", "")
        _package(git_repo, "src/app", files=["main.py"], with_spec=True)
        _package(git_repo, "src/app/plugins", files=["hook.py"])
        result = run_recommend(git_repo)
        scopes = [row.scope_dir.as_posix() for row in result.rows]
        assert scopes == ["src/app/plugins"]
        assert "Nested Python package" in result.rows[0].rationale

    def test_nested_without_init_is_skipped(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", "")
        _package(git_repo, "src/app", files=["main.py"], with_spec=True)
        nested = git_repo / "src" / "app" / "data"
        nested.mkdir(parents=True)
        write_text(nested / "load.py", "x\n")
        result = run_recommend(git_repo)
        assert result.rows == ()

    def test_ranks_by_py_file_count(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", "")
        _package(git_repo, "src/small", files=["a.py"])
        _package(git_repo, "src/large", files=["a.py", "b.py", "c.py"])
        result = run_recommend(git_repo)
        assert [row.scope_dir.as_posix() for row in result.rows] == [
            "src/large",
            "src/small",
        ]

    def test_skips_egg_info_and_ignored(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", "ignore:\n  - vendor\n")
        _package(git_repo, "src/ok", files=["a.py"])
        (git_repo / "src" / "ok.egg-info").mkdir(parents=True)
        write_text(git_repo / "src" / "ok.egg-info" / "PKG-INFO", "n")
        _package(git_repo, "src/vendor", files=["a.py"])
        result = run_recommend(git_repo)
        assert [row.scope_dir.as_posix() for row in result.rows] == ["src/ok"]

    def test_empty_when_no_src(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", "")
        result = run_recommend(git_repo)
        assert result.rows == ()

    def test_missing_project_raises(self) -> None:
        with git_repository() as repo, pytest.raises(RecommendError) as caught:
            run_recommend(repo)
        assert "codoc.yaml not found" in str(caught.value)

    def test_agent_ranker_falls_back_without_key(self) -> None:
        rows = (
            SpecRecommendation(Path("src/a"), "a", py_files=1),
            SpecRecommendation(Path("src/b"), "b", py_files=5),
        )
        ranker = AgentRanker(LlmConfig(provider="openai", model="gpt-4.1"))
        with patch.dict("os.environ", {}, clear=True):
            ranked = ranker.rank(rows)
        assert [row.scope_dir.as_posix() for row in ranked] == ["src/b", "src/a"]
        assert ranker.ranking == "heuristic"
        assert ranker.note is not None
        assert "no API key" in ranker.note

    def test_agent_ranker_uses_llm_order(self) -> None:
        rows = (
            SpecRecommendation(Path("src/a"), "a", py_files=1),
            SpecRecommendation(Path("src/b"), "b", py_files=5),
        )

        def fake_chat(**_kwargs: object) -> str:
            return '["src/a", "src/b"]'

        ranker = AgentRanker(
            LlmConfig(provider="openai", model="gpt-4.1"),
            chat=fake_chat,
        )
        with patch("codoc.commands.recommend.resolve_api_key", return_value="sk-test"):
            ranked = ranker.rank(rows)
        assert [row.scope_dir.as_posix() for row in ranked] == ["src/a", "src/b"]
        assert ranker.ranking == "agent"

    def test_agent_ranker_falls_back_on_llm_error(self) -> None:
        rows = (SpecRecommendation(Path("src/a"), "a", py_files=1),)

        def boom(**_kwargs: object) -> str:
            raise LlmError("nope")

        ranker = AgentRanker(
            LlmConfig(provider="openai", model="gpt-4.1"),
            chat=boom,
        )
        with patch("codoc.commands.recommend.resolve_api_key", return_value="sk-test"):
            ranked = ranker.rank(rows)
        assert ranked == HeuristicRanker().rank(rows)
        assert ranker.ranking == "heuristic"
        assert ranker.note is not None
        assert "failed" in ranker.note

    def test_cli_prints_table(self, git_repo: Path) -> None:
        run_init(git_repo)
        _package(git_repo, "src/extra", files=["mod.py"])
        out, err, code = run_cli(git_repo, ["recommend"])
        assert code in (0, None)
        assert out.splitlines()[0] == "scope_dir\trationale"
        assert any(line.startswith("src/extra\t") for line in out.splitlines())

    @pytest.mark.parametrize("argv", [["recommend"]])
    def test_cli_outside_repo_exits_1(self, tmp_dir: Path, argv: list[str]) -> None:
        out, err, code = run_cli(tmp_dir, argv)
        assert code == 1
        assert out == ""
        assert "codoc recommend:" in err
