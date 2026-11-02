PYTHON = .venv/bin/python

.PHONY: install examples run test lint coverage

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt

examples:
	$(PYTHON) -m examples.demo

run:
	$(PYTHON) -m uvicorn src.server:app --host 127.0.0.1 --port 8000

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m pycodestyle src examples tests --max-line-length=80

coverage:
	$(PYTHON) -m coverage run --branch \
		--source=src.server,src.client,src.model,src.xml_codec \
		-m pytest -q tests/test_api_stateful.py
	$(PYTHON) -m coverage report -m \
		--include='src/server.py,src/client.py,src/model.py,src/xml_codec.py'
