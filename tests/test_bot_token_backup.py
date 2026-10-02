import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

importlib.import_module("heroku.main")
_without_inline_bot_token = importlib.import_module(
    "heroku.Modules.Backup"
)._without_inline_bot_token


source = {
    "heroku.inline": {"bot_token": "first", "enabled": True},
    "nested": [{"BOT_TOKEN": "second", "value": 1}],
    "tuple": ({"bot_token": "third"},),
}
clean = _without_inline_bot_token(source)
assert clean == {
    "heroku.inline": {"enabled": True},
    "nested": [{"BOT_TOKEN": "second", "value": 1}],
    "tuple": ({"bot_token": "third"},),
}
assert source["heroku.inline"]["bot_token"] == "first"
