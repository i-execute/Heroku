import importlib
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

importlib.import_module("heroku.main")
loader = importlib.import_module("heroku.loader")


def source(version):
    return (
        "from heroku import loader\n"
        "class Persisted(loader.Module):\n"
        f"    version = {version}\n"
    ).encode()


directory = Path(tempfile.mkdtemp())
with patch.object(loader, "MODULES_PATH", directory), patch.object(
    loader, "MODULES_DIR", str(directory)
):
    stale = directory / "Persisted_123.py"
    stale.write_bytes(source(1))
    saved = loader.save_module_source(source(2), "Persisted")
    assert saved == directory / "Persisted.py"
    assert saved.read_bytes() == source(2)
    assert list(directory.glob("*.py")) == [saved]

    saved.write_bytes(source(2))
    duplicate = directory / "Persisted_456.py"
    duplicate.write_bytes(source(3))
    os.utime(saved, ns=(1, 1))
    os.utime(duplicate, ns=(2, 2))
    selected = loader._external_module_files()
    assert selected == [saved.resolve()]
    assert saved.read_bytes() == source(3)
    assert list(directory.glob("*.py")) == [saved]

    removed = loader.remove_module_source("Persisted")
    assert removed == [saved]
    assert not list(directory.glob("*.py"))
