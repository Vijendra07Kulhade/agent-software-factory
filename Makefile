PYTHON ?= python3
.PHONY: test validate-cron

test:
	$(PYTHON) -m unittest discover -s tests -v

validate-cron:
	$(PYTHON) skills/cron-job/scripts/validate_job.py skills/cron-job/templates/job.example.json
