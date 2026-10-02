#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PARENT_PID="$PPID"
PARENT_COMMAND="$(ps -p "$PARENT_PID" -o args= 2>/dev/null || true)"

if [ ! -f "$ROOT_DIR/heroku/__main__.py" ]; then
    printf '%s\n' "Refusing to remove an invalid installation path: $ROOT_DIR" >&2
    exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
    systemctl disable heroku.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/heroku.service
    rm -f /etc/systemd/system/multi-user.target.wants/heroku.service
    systemctl daemon-reload >/dev/null 2>&1 || true
    rm -rf -- "$ROOT_DIR"
    systemctl stop heroku.service >/dev/null 2>&1 || true
else
    systemctl --user disable heroku.service >/dev/null 2>&1 || true
    rm -f "$HOME/.config/systemd/user/heroku.service"
    rm -f "$HOME/.config/systemd/user/default.target.wants/heroku.service"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    rm -rf -- "$ROOT_DIR"
    systemctl --user stop heroku.service >/dev/null 2>&1 || true
fi

if printf '%s' "$PARENT_COMMAND" | grep -Eq 'python([^ ]*)? .*[-]m heroku'; then
    kill -TERM "$PARENT_PID" >/dev/null 2>&1 || true
fi

printf '%s\n' "Heroku userbot removed."
