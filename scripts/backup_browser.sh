#!/bin/bash
# Daily: pull latest list (after GitHub refresh 03:17 UTC) then mirror new browser games into /workspace/downloads
set -u
exec 9>/workspace/downloads/logs/backup_browser.lock; flock -n 9 || { echo "already running"; exit 0; }
cd /workspace/awesome-decomp-games && git pull --ff-only -q || echo "git pull failed, using local data"
python3 scripts/backup_browser.py "$@"
