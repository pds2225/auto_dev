from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

TEST_TEMP_ROOT = Path(r"C:\Users\Public\Documents\ESTsoft\CreatorTemp\auto_dev_tests_manual")
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

os.environ["TMP"] = str(TEST_TEMP_ROOT)
os.environ["TEMP"] = str(TEST_TEMP_ROOT)
tempfile.tempdir = str(TEST_TEMP_ROOT)


class _SafeTemporaryDirectory:
    def __init__(self, suffix: str = "", prefix: str = "tmp", dir: str | None = None):
        base_dir = Path(dir) if dir else TEST_TEMP_ROOT
        self.name = str(base_dir / f"{prefix}{uuid.uuid4().hex}{suffix}")
        Path(self.name).mkdir(parents=True, exist_ok=False)

    def __enter__(self):
        return self.name

    def __exit__(self, exc_type, exc, tb):
        shutil.rmtree(self.name, ignore_errors=True)
        return False


tempfile.TemporaryDirectory = _SafeTemporaryDirectory
