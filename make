#!/usr/bin/env bash
# Shim for hosts without GNU make (DECISIONS D-002). Usage: ./make <target> [VAR=value]
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; elif [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; else PY=python3; fi
exec "$PY" scripts/tasks.py "$@"
