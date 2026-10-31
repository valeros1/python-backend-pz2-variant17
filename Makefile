PYTHON = .venv/bin/python

.PHONY: install examples test lint

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt

examples:
	$(PYTHON) -m examples.demo

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m pycodestyle src examples tests --max-line-length=80
