"""restore: .py from archive + modules by URL from db_mods.json (old-bot backups)."""
import asyncio
import io
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import orjson


def build_backup(tmp: Path, with_db_mods: bool, dead_url: str | None = None) -> bytes:
    mods = io.BytesIO()
    with zipfile.ZipFile(mods, "w") as mz:
        mz.writestr("FromFile_123.py", b"# mod from archive")
        mz.writestr("db_mods.json", orjson.dumps({
            "FromFile": "https://x.invalid/FromFile.py",
            "ByUrl": "https://x.invalid/ByUrl.py",
            **({"Dead": dead_url} if dead_url else {}),
        }))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as az:
        az.writestr("db.json", orjson.dumps({"heroku.security": {}}))
        az.writestr("mods.zip", mods.getvalue())
    return archive.getvalue()


async def run_restore(archive: bytes, loaded_dir: Path, fetches: dict) -> tuple:
    import heroku.main  # noqa: F401
    from heroku import loader, utils
    from heroku.Modules.Backup import Backup

    with (
        patch.object(loader, "LOADED_MODULES_PATH", loaded_dir),
        patch.object(utils, "run_sync", lambda fn, *a, **kw: _async(fn(*a, **kw))),
    ):
        class R:
            def __init__(self, c, t):
                self.status_code, self.content = c, t

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(self.status_code)

        class Req:
            @staticmethod
            def get(url, timeout=30, **kw):
                c, t = fetches.get(url, (404, b""))
                return R(c, t)

        async def _async(v):
            return v

        mod = Backup.__new__(Backup)
        mod.strings = {
            "reply_to_file": "REPLY",
            "restoring_backup": "RESTORING",
            "db_restored": "DBOK",
            "all_restored": "ALLOK",
        }
        mod._db = type("DB", (), {
            "process_db_autofix": lambda s, d: True,
            "clear": lambda s: None,
            "update": lambda s, **kw: None,
            "save": lambda s: None,
        })()
        mod.invoke = lambda *a, **kw: _async(None)

        class M:
            peer_id = None

        class Reply:
            media = True
            @staticmethod
            async def download_media(_):
                return archive

        msg = M()
        msg.get_reply_message = lambda: _async(Reply())
        with patch.object(utils, "answer", lambda *a, **kw: _async(a[0] if a else None)):
            with patch.object(sys.modules["heroku.Modules.Backup"], "requests", Req):
                await Backup.restore(mod, msg)

    files = sorted(p.stem for p in loaded_dir.glob("*.py"))
    return files


async def main():
    import tempfile

    # 1: happy path — archive file + url module fetched, dead link skipped
    d1 = Path(tempfile.mkdtemp())
    files = await run_restore(
        build_backup(d1, True, "https://x.invalid/dead.py"),
        d1,
        {"https://x.invalid/ByUrl.py": (200, b"# by url")},
    )
    assert files == ["ByUrl", "FromFile_123"], files
    assert (d1 / "ByUrl.py").read_bytes() == b"# by url"
    assert not (d1 / "FromFile.py").exists(), "file from archive must win over url"
    assert not (d1 / "Dead.py").exists()

    # 2: archive without db_mods.json — old path intact
    d2 = Path(tempfile.mkdtemp())
    files = await run_restore(build_backup(d2, False), d2, {})
    assert files == ["FromFile_123"], files

    print("restore backup E2E OK: 2 cases")


asyncio.run(main())
