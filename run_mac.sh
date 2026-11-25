#!/bin/bash
# Start ClassEye on macOS / Linux:   bash run_mac.sh
cd "$(dirname "$0")"
[ -d venv ] || { echo "Run: bash setup_mac.sh   first."; exit 1; }
source venv/bin/activate
# Quietly add any library a new version needs (skipped when offline)
python -m pip install -q --disable-pip-version-check -r requirements.txt >/dev/null 2>&1 || echo " (Could not check for new libraries - starting anyway)"
python app.py
