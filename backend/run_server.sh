#!/bin/bash
set -euo pipefail

if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
fi
uvicorn app.main:app --reload
