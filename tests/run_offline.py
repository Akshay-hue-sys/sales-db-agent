"""The only approved default test entry point; guards precede pytest collection."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from offline_guard import install

if __name__ == "__main__":
    install()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root))
    import pytest

    with TemporaryDirectory(prefix="sales-offline-") as temp:
        code = pytest.main(
            ["-q", "-p", "no:cacheprovider", "--basetemp", str(Path(temp) / "pytest"), str(root / "tests" / "offline")]
        )
    raise SystemExit(code)
