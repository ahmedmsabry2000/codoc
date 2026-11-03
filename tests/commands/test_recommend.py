from pathlib import Path

import pytest

from codoc.commands.init import run_init
from codoc.commands.recommend import (
    AgentRanker,
    HeuristicRanker,
    RecommendError,
    SpecRecommendation,
    run_recommend,
)
from tests.support.cli import run_cli
from tests.support.fs import write_text
from tests.support.git import git_repository


def _package(repo: Path, name: str, *, files: list[str], with_spec: bool = False) -> Path:
    pkg = repo / "src" / name
    pkg.mkdir(parents=True)
    write_text(pkg / "__init__.py", "")
    for rel in files:
        write_text(pkg / rel, f"# {rel}\n")
    if with_spec:
        write_text(pkg / "codoc.spec.yaml", "docs: []\ncoverage:\n  source: []\n")
    return pkg


class RecommendTests:
    def test_lists_src_packages_without_spec(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", "engine:\n  name: zensical\n")
        _package(git_repo, "widgets", files=["a.py", "b.py"])
        _package(git_repo, "core", files=["x.py"], with_spec=True)
        result = run_recommend(git_repo)
        scopes = [row.scope_dir.as_posix() for row in result.rows]
        assert scopes == ["src/widgets"]
        assert "without codoc.spec.yaml" in result.rows[0].rationale
        assert "3 .py files" in result.rows[0].rationale

    def test_ranks_by_py_file_count(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", "")
        _package(git_repo, "small", files=["a.py"])
        _package(git_repo, "large", files=["a.py", "b.py", "c.py"])
        result = run_recommend(git_repo)
        assert [row.scope_dir.as_posix() for row in result.rows] == [
            "src/large",
            "src/small",
        ]

    def test_skips_egg_info_and_ignored(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", "ignore:\n  - vendor\n")
        _package(git_repo, "ok", files=["a.py"])
        (git_repo / "src" / "ok.egg-info").mkdir(parents=True)
        write_text(git_repo / "src" / "ok.egg-info" / "PKG-INFO", "n")
        _package(git_repo, "vendor", files=["a.py"])
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

    def test_agent_ranker_falls_back_to_heuristic(self) -> None:
        rows = (
            SpecRecommendation(Path("src/a"), "a", py_files=1),
            SpecRecommendation(Path("src/b"), "b", py_files=5),
        )
        ranked = AgentRanker().rank(rows)
        assert [row.scope_dir.as_posix() for row in ranked] == ["src/b", "src/a"]
        assert HeuristicRanker().rank(rows) == ranked

    def test_cli_prints_table(self, git_repo: Path) -> None:
        run_init(git_repo)
        # init creates a starter spec under src/<pkg>; add a second package without one
        _package(git_repo, "extra", files=["mod.py"])
        out, err, code = run_cli(git_repo, ["recommend"])
        assert code in (0, None)
        assert err == ""
        assert out.splitlines()[0] == "scope_dir\trationale"
        assert any(line.startswith("src/extra\t") for line in out.splitlines())

    @pytest.mark.parametrize(
        "argv",
        [["recommend"]],
    )
    def test_cli_outside_repo_exits_1(self, tmp_dir: Path, argv: list[str]) -> None:
        out, err, code = run_cli(tmp_dir, argv)
        assert code == 1
        assert out == ""
        assert "codoc recommend:" in err
