#!/bin/bash
# ClassEye - one-time setup on macOS / Linux.   bash setup_mac.sh
set -e
cd "$(dirname "$0")"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
if [ ! -f models/yolov8n-pose.onnx ]; then
  python3 -m venv venv_models
  venv_models/bin/python -m pip install -q --upgrade pip
  venv_models/bin/python tools/get_models.py
else
  python tools/get_models.py --faces
fi
echo "Setup complete. Start ClassEye with:  source venv/bin/activate && python app.py"
