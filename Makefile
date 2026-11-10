PYTHON ?= python3
.PHONY: test demo verify
test:
	$(PYTHON) -m unittest discover -s tests -v
demo:
	$(PYTHON) -m factory demo --scenario roas-unit-mismatch --out artifacts/roas
	$(PYTHON) -m factory demo --scenario campaign-confirmation --out artifacts/campaign
	$(PYTHON) -m factory demo --scenario upstream-timeout --out artifacts/timeout
verify:
	$(PYTHON) -m factory verify --bundle artifacts/roas
	$(PYTHON) -m factory verify --bundle artifacts/campaign
