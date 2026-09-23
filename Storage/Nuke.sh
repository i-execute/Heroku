#!/bin/bash
if [ "$(id -u)" -eq 0 ]; then
    systemctl stop heroku 2>/dev/null
    systemctl disable heroku 2>/dev/null
    rm -f /etc/systemd/system/heroku.service
    systemctl daemon-reload
else
    systemctl --user stop heroku 2>/dev/null
    systemctl --user disable heroku 2>/dev/null
    rm -f ~/.config/systemd/user/heroku.service
    systemctl --user daemon-reload
fi
rm -rf ~/Heroku
echo "Heroku userbot removed."
