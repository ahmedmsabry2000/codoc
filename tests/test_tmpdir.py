import os
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.tmpdir import _REPO_ROOT, safe_temp_root, temporary_directory


class TmpdirTests(unittest.TestCase):
    def test_safe_temp_root_skips_tmpdir_inside_repo(self) -> None:
        poisoned = _REPO_ROOT / "src"
        with patch.dict(os.environ, {"TMPDIR": str(poisoned)}):
            root = safe_temp_root()
        self.assertFalse(root.is_relative_to(_REPO_ROOT))
        self.assertTrue(root.is_dir())

    def test_temporary_directory_is_outside_repo(self) -> None:
        poisoned = _REPO_ROOT / "src"
        with patch.dict(os.environ, {"TMPDIR": str(poisoned)}):
            with temporary_directory() as path:
                self.assertFalse(path.resolve().is_relative_to(_REPO_ROOT))
                self.assertTrue(path.is_dir())


if __name__ == "__main__":
    unittest.main()
