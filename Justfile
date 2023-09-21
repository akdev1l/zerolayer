install:
	python3 -m poetry build
	pip install -U dist/zerolayer*.whl

dev-install:
	pip install -e .
	zerolayer

test:
	# TODO: integrate testing
	pytest tests
