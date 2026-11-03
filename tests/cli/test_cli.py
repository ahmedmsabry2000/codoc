import io
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

import codoc.cli as cli
from codoc.discover import git_root
from tests.support.fs import write_text
from tests.support.git import git_repository


def _run_status_in(path: Path) -> tuple[str, str, int | None, Path]:
    previous = os.getcwd()
    os.chdir(path)
    stdout = io.StringIO()
    stderr = io.StringIO()
    code: int | None = None
    try:
        cwd = Path.cwd()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                cli.main(["status"])
            except SystemExit as caught:
                status = caught.code
                code = status if isinstance(status, int) else None
        return stdout.getvalue(), stderr.getvalue(), code, cwd
    finally:
        os.chdir(previous)


class CliTests:
    def test_bare_invocation_prints_help_and_exits_zero(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), pytest.raises(SystemExit) as caught:
            cli.main([])
        assert caught.value.code == 0
        self._assert_help_lists_commands(stdout.getvalue())

    def test_help_flag_exits_zero(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), pytest.raises(SystemExit) as caught:
            cli.main(["--help"])
        assert caught.value.code == 0
        self._assert_help_lists_commands(stdout.getvalue())

    def test_unimplemented_commands_print_not_implemented_to_stderr(self) -> None:
        for command in cli.COMMANDS:
            if command.name in {"init", "status", "build", "serve", "lint", "clean"}:
                continue
            stderr = io.StringIO()
            with redirect_stderr(stderr), pytest.raises(SystemExit) as caught:
                cli.main([command.name])
            assert caught.value.code == 2
            assert stderr.getvalue() == f"codoc {command.name}: not implemented\n"

    def test_status_prints_tsv_and_exits_zero(self) -> None:
        with git_repository() as repo:
            write_text(repo / "codoc.yaml")
            write_text(repo / "codoc.spec.yaml")
            write_text(repo / "src" / "my_project" / "codoc.spec.yaml")
            write_text(repo / "src" / "my_project" / "api" / "codoc.spec.yaml")
            write_text(repo / "src" / "my_project" / "cli" / "codoc.spec.yaml")
            stdout, stderr, code, _cwd = _run_status_in(repo)
        assert code is None
        assert stderr == ""
        assert stdout == "\n".join(
            (
                "spec_path\tscope_dir\tpages",
                "codoc.spec.yaml\t.\t0",
                "src/my_project/api/codoc.spec.yaml\tsrc/my_project/api\t0",
                "src/my_project/cli/codoc.spec.yaml\tsrc/my_project/cli\t0",
                "src/my_project/codoc.spec.yaml\tsrc/my_project\t0",
                "registry_pages\t0",
                "",
            )
        )

    def test_status_with_no_specs_prints_the_header(self) -> None:
        with git_repository() as repo:
            write_text(repo / "codoc.yaml")
            stdout, stderr, code, _cwd = _run_status_in(repo)
        assert code is None
        assert stderr == ""
        assert stdout == "spec_path\tscope_dir\tpages\nregistry_pages\t0\n"

    def test_status_outside_a_repo_exits_1(self, tmp_dir: Path) -> None:
        stdout, stderr, code, cwd = _run_status_in(tmp_dir)
        assert code == 1
        assert stdout == ""
        assert stderr == f"codoc status: not a git repository at {cwd}\n"

    def test_status_without_codoc_yaml_exits_1(self) -> None:
        with git_repository() as repo:
            root = git_root(repo)
            stdout, stderr, code, _cwd = _run_status_in(repo)
        assert code == 1
        assert stdout == ""
        assert stderr == f"codoc status: codoc.yaml not found at {root / 'codoc.yaml'}\n"

    def test_status_prints_page_counts(self) -> None:
        spec = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    type: manual",
                "    path: docs/overview.md",
                "  - id: build-serve-loop",
                "    type: hybrid",
                "    path: docs/guides/build-serve.md",
                "coverage:",
                "  source:",
                "    - id: cli-core",
                "      type: auto-generated",
                "      paths: []",
                "      docs:",
                "        - id: cli-core.ref",
                "          path: docs/reference/cli/index.md",
                "",
            )
        )
        root_spec = "\n".join(
            (
                "docs:",
                "  - id: readme",
                "    type: manual",
                "    path: docs/readme.md",
                "",
            )
        )
        with git_repository() as repo:
            write_text(repo / "codoc.yaml")
            write_text(repo / "codoc.spec.yaml", root_spec)
            write_text(repo / "src" / "my_project" / "cli" / "codoc.spec.yaml", spec)
            stdout, stderr, code, _cwd = _run_status_in(repo)
        assert code is None
        assert stderr == ""
        assert stdout == "\n".join(
            (
                "spec_path\tscope_dir\tpages",
                "codoc.spec.yaml\t.\t1",
                "src/my_project/cli/codoc.spec.yaml\tsrc/my_project/cli\t3",
                "registry_pages\t4",
                "",
            )
        )

    def test_status_unknown_project_key_exits_1(self) -> None:
        with git_repository() as repo:
            write_text(repo / "codoc.yaml", "serve: true\n")
            root = git_root(repo)
            stdout, stderr, code, _cwd = _run_status_in(repo)
        assert code == 1
        assert stdout == ""
        assert stderr == f"codoc status: {root / 'codoc.yaml'}: document: unknown field 'serve'\n"

    def test_status_invalid_spec_exits_1(self) -> None:
        spec = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    type: essay",
                "    path: docs/overview.md",
                "",
            )
        )
        with git_repository() as repo:
            write_text(repo / "codoc.yaml")
            write_text(repo / "codoc.spec.yaml", spec)
            root = git_root(repo)
            stdout, stderr, code, _cwd = _run_status_in(repo)
        assert code == 1
        assert stdout == ""
        assert stderr == (
            "codoc status: "
            f"{root / 'codoc.spec.yaml'}: "
            "docs[0].type: expected manual, hybrid, or auto-generated\n"
        )

    def test_status_duplicate_page_id_across_specs_exits_1(self) -> None:
        spec = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    type: manual",
                "    path: docs/overview.md",
                "",
            )
        )
        with git_repository() as repo:
            write_text(repo / "codoc.yaml")
            write_text(repo / "codoc.spec.yaml", spec)
            write_text(repo / "src" / "codoc.spec.yaml", spec)
            root = git_root(repo)
            stdout, stderr, code, _cwd = _run_status_in(repo)
        earlier = root / "codoc.spec.yaml"
        later = root / "src" / "codoc.spec.yaml"
        assert code == 1
        assert stdout == ""
        assert stderr == f"codoc status: {later}: duplicate page id 'overview' also in {earlier}\n"

    def test_drift_alias_prints_validate_not_implemented(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr), pytest.raises(SystemExit) as caught:
            cli.main(["drift"])
        assert caught.value.code == 2
        assert stderr.getvalue() == "codoc validate: not implemented\n"

    def test_aliases_point_at_existing_commands(self) -> None:
        by_name = {command.name: command for command in cli.COMMANDS}
        for command in cli.COMMANDS:
            for alias in command.aliases:
                assert alias not in by_name
        validate = by_name["validate"]
        assert validate.aliases == ("drift",)

    def _assert_help_lists_commands(self, text: str) -> None:
        assert "usage: codoc" in text
        normalized = " ".join(text.split())
        for command in cli.COMMANDS:
            assert command.name in text
            assert command.summary in normalized
        assert "drift" in text
