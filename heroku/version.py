# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

__version__ = (2, 2, 2)

import os

NO_GIT = os.environ.get("HEROKU_NO_GIT") == "1"
if not NO_GIT:
    import git
else:
    git = None

if NO_GIT:
    branch = "master"
else:
    try:
        assert git is not None
        with git.Repo(
            path=os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        ) as repo:
            branch = repo.active_branch.name
    except Exception:
        branch = "master"
