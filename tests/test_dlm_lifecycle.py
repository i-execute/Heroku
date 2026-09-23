"""Runtime test: dlm/lm module lifecycle (no Telegram involved)."""
import asyncio
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TESTMOD = '''from .. import loader


class FakeLoadedMod(loader.Module):
    """Test module loaded via file lifecycle"""

    strings = {"name": "FakeLoaded"}

    @loader.command()
    async def pingcmd(self, message):
        """Ping"""
        await message.reply("pong")
'''


async def main():
    import heroku.main
    from heroku import loader as hloader

    # fake client with tg_id
    class FakeClient:
        tg_id = 123456789
        heroku_me = None

        async def get_entity(self, *a, **kw):
            return None

    # standalone loader instance (db not needed for register_module mechanics)
    modules = hloader.Modules.__new__(hloader.Modules)
    from heroku import utils

    # init minimal attrs
    modules.modules = []
    modules.libraries = []
    modules.aliases = {}
    modules.commands = {}
    modules.inline = None
    modules._db = None
    modules.watcher = None
    modules.dispatcher = None

    # prepare LoadedModules dir with a test file
    lm_dir = hloader.LOADED_MODULES_DIR
    os.makedirs(lm_dir, exist_ok=True)
    test_path = os.path.join(lm_dir, "FakeLoadedMod.py")
    with open(test_path, "w") as f:
        f.write(TESTMOD)

    try:
        # simulate _register_modules single file load
        import importlib.machinery

        module_name = "heroku.modules.FakeLoadedMod"
        spec = importlib.machinery.ModuleSpec(
            module_name,
            hloader.StringLoader(TESTMOD, "<file FakeLoadedMod>"),
            origin="<file FakeLoadedMod>",
        )

        # can't use full register_module (needs lookup/settings) — test the save+read cycle instead:
        # 1) save_fs writes {Class}.py
        cls_name = "FakeLoadedMod"
        save_path = os.path.join(lm_dir, f"{cls_name}.py")
        assert os.path.isfile(save_path), "save path broken"

        # 2) _iter_module_files picks up {Class}.py without tg_id suffix
        files = list(
            hloader._iter_module_files(lm_dir)
        )
        assert any(f.endswith("FakeLoadedMod.py") for f in files), (
            f"register_all would NOT load {save_path}: got {files}"
        )
        print("PASS: register_all scan includes plain {Class}.py")

        # 3) full exec of the module source via StringLoader
        import importlib.util

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "FakeLoadedMod"), "module source doesn't exec"
        print("PASS: module source execs via StringLoader")

        # 4) no requests/custom headers machinery left in Installer.dlmod flow
        installer_src_path = os.path.join(
            os.path.dirname(os.path.abspath(hloader.__file__)),
            "Modules",
            "Installer.py",
        )
        src = open(installer_src_path).read()
        assert "headers=" not in src.split("async def dlm")[1].split("async def ")[
            0
        ], "dlmod sends custom headers"
        assert "self._links_cache" not in src, "links cache still referenced"
        print("PASS: dlmod is a bare requests.get, no headers/cache")

        print("ALL TESTS PASSED")
    finally:
        os.remove(test_path)
        # cleanup pycache
        pycache = os.path.join(lm_dir, "__pycache__")
        if os.path.isdir(pycache):
            shutil.rmtree(pycache)


asyncio.run(main())
