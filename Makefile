.pydeps: requirements.txt
	pip install -r requirements.txt
	touch .pydeps

.PHONY: dev
dev: .pydeps
	honcho start

.PHONY: redis-py-shell
redis-py-shell: .pydeps
	python -i -c 'from redis import StrictRedis; redis=StrictRedis("$(REDIS_HOST)")'

.PHONY: docker
docker:
	docker build -t hypothesis/badger .
