@echo off
rem Shim for hosts without GNU make (DECISIONS D-002). Usage: make <target> [VAR=value]
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\tasks.py" %*
