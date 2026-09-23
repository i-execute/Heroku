"""dlm no-args = dlmall: repo -> full.txt -> install all."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = "https://modules.invalid/repo"


class Resp:
    def __init__(self, text, code=200):
        self.text = text
        self.status_code = code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(str(self.status_code))


async def main():
    import heroku.main  # noqa: F401
    import heroku.utils as u
    import requests as real_requests
    from heroku.Modules.Installer import Installer as InstallerMod
    import heroku.Modules.Installer as I

    inst = InstallerMod.__new__(InstallerMod)
    inst.config = {"modules_repo": REPO}
    inst.strings = {
        "dlmall_no_repo": "SET REPO",
        "dlmall_start": "START {}",
        "dlmall_failed": "FAILED {} {} {}",
        "dlmall_done": "DONE {}",
        "no_module": "NO",
        "installing": "INSTALL {}",
    }

    loaded = []

    async def fake_load(doc, message, origin="<string>", save_fs=True, **kw):
        loaded.append(origin)
        return "Broken" not in origin

    inst.load_module = fake_load

    replies = []

    async def answer(msg, text, *a, **kw):
        replies.append(text)
        return msg

    def mk_req(files):
        def get(url, timeout=30, **kw):
            if url in files:
                return files[url]
            return files.get(url[len(REPO):], Resp(None, 404))

        return type(
            "R",
            (),
            {
                "get": staticmethod(get),
                "exceptions": real_requests.exceptions,
            },
        )

    msg = object()

    async def run(args, files):
        replies.clear()
        with (
            patch.object(u, "get_args_raw", return_value=args),
            patch.object(u, "answer", answer),
            patch.object(I, "requests", mk_req(files)),
        ):
            await InstallerMod.dlm(inst, msg)
        return replies[-1]

    MOD = "code"

    # 1: mixed -> FAILED installed total list
    files = {
        "/full.txt": Resp("DlmTest\nBroken\n"),
        "/DlmTest.py": Resp(MOD),
        "/Broken.py": Resp(MOD),
    }
    loaded.clear()
    r = await run("", files)
    assert loaded == [f"{REPO}/DlmTest.py", f"{REPO}/Broken.py"], loaded
    assert "FAILED 1 2" in r, r

    # 2: all ok -> DONE n
    files = {"/full.txt": Resp("DlmTest\n"), "/DlmTest.py": Resp(MOD)}
    r = await run("", files)
    assert "DONE 1" in r, r

    # 3: repo unset -> ask to set
    inst.config = {"modules_repo": ""}
    r = await run("", {"/full.txt": Resp("DlmTest\n")})
    assert r == "SET REPO", r

    # 4: full.txt missing -> NO
    inst.config = {"modules_repo": REPO}
    r = await run("", {})
    assert r == "NO", r

    # 5: url arg -> single-module path still works (origin stays default)
    inst.config = {"modules_repo": ""}
    loaded.clear()
    r = await run(f"{REPO}/x.py", {"/x.py": Resp(MOD)})
    assert loaded == ["<string>"], loaded

    # 6: github.com repo url -> raw.githubusercontent fetch
    RAW = "https://raw.githubusercontent.com/i-execute/Modules/main"
    files = {f"{RAW}/full.txt": Resp("DlmTest\n"), f"{RAW}/DlmTest.py": Resp(MOD)}
    inst.config = {"modules_repo": "github.com/i-execute/Modules"}
    r = await run("", files)
    assert "DONE 1" in r, r

    print("dlm/dlmall E2E OK: 6 cases")


asyncio.run(main())
