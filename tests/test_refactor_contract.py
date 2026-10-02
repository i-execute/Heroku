import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def decorator_name(decorator):
    if isinstance(decorator, ast.Call):
        decorator = decorator.func
    return decorator.attr if isinstance(decorator, ast.Attribute) else ""


def main():
    importlib.import_module("heroku.main")
    from heroku import loader, utils, validators
    from heroku.inline.form import _input_title_symbol

    assert {path.name for path in (ROOT / "Storage").iterdir()} == {
        "Heroku.PNG",
        "requirements.txt",
        "Nuke.sh",
    }

    class English(loader.Module):
        strings_ru = {"name": "Russian"}

        class Strings_en:
            name = "English"
            value = "Selected"

    class Russian(loader.Module):
        Strings_ru = {"name": "Russian"}

    class Fallback(loader.Module):
        other_strings = {"name": "Fallback"}

    assert loader.Modules._select_module_strings(English()) == {
        "name": "English",
        "value": "Selected",
    }
    assert loader.Modules._select_module_strings(Russian())["name"] == "Russian"
    assert loader.Modules._select_module_strings(Fallback())["name"] == "Fallback"
    assert isinstance(validators.RandomLink().doc, str)
    assert utils.normalize_prefix("!") == "!"
    assert utils.normalize_prefix("!!") == "."
    assert utils.normalize_prefix(1) == "."

    expected = "ABXY↑↓←→↑↓←→ABXY"
    assert "".join(_input_title_symbol(index) for index in range(16)) == expected

    modules = ROOT / "heroku" / "Modules"
    executor_source = (modules / "Executor.py").read_text()
    assert "inline_handler" not in executor_source
    assert "InlineShellEditor" not in executor_source
    assert "_ShellSession" not in executor_source

    security_tree = ast.parse((modules / "Security.py").read_text())
    commands = {
        node.name
        for node in ast.walk(security_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(decorator_name(item) == "command" for item in node.decorator_list)
    }
    assert commands == {"owner"}

    backup_tree = ast.parse((modules / "Backup.py").read_text())
    handler = next(
        node
        for node in ast.walk(backup_tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "handler"
    )
    loop = next(
        item
        for item in handler.decorator_list
        if isinstance(item, ast.Call) and decorator_name(item) == "loop"
    )
    keywords = {item.arg: ast.literal_eval(item.value) for item in loop.keywords}
    assert keywords == {"interval": 3600, "autostart": True}

    for path in modules.glob("*.py"):
        source = path.read_text()
        assert "rich_message" not in source
        assert "rich_mode" not in source
    translate_source = (modules / "Translate.py").read_text()
    assert "TranslateTextRequest" in translate_source
    assert "GoogleTranslator" not in translate_source
    assert not (ROOT / "heroku" / "translations.py").exists()
    assert (modules / "Tester.py").exists()
    assert not (modules / "Test.py").exists()


if __name__ == "__main__":
    main()
