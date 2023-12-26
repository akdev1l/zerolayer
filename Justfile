install:
	python3 -m venv .venv
	.venv/bin/pip install -U . poetry
	@echo "Now you may source .venv/bin/activate to run zerolayer or add .local/bin to your PATH variable"

dev-install:
	python3 -m venv .venv
	.venv/bin/pip install -e .
	@echo "Now you should source .venv/bin/activate for your shell"

test:
	# TODO: integrate testing
	pytest tests
