# All targets delegate to scripts/tasks.py (DECISIONS D-002).
PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,$(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,python3))
TARGETS := setup lint test local deploy destroy eval bench final-check verify-aws validate-dataset calibrate node-quality
.PHONY: $(TARGETS)
$(TARGETS):
	$(PY) scripts/tasks.py $@ $(if $(ZONE),ZONE=$(ZONE)) $(if $(HOURS),HOURS=$(HOURS))
