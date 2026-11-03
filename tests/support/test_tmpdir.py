import os
from unittest.mock import patch

from tests.support.tmpdir import _REPO_ROOT, safe_temp_root, temporary_directory


class TmpdirTests:
    def test_safe_temp_root_skips_tmpdir_inside_repo(self) -> None:
        poisoned = _REPO_ROOT / "src"
        with patch.dict(os.environ, {"TMPDIR": str(poisoned)}):
            root = safe_temp_root()
        assert not root.is_relative_to(_REPO_ROOT)
        assert root.is_dir()

    def test_temporary_directory_is_outside_repo(self) -> None:
        poisoned = _REPO_ROOT / "src"
        with (
            patch.dict(os.environ, {"TMPDIR": str(poisoned)}),
            temporary_directory() as path,
        ):
            assert not path.resolve().is_relative_to(_REPO_ROOT)
            assert path.is_dir()
