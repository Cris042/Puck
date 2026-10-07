# Alvos da base técnica (seção 7). Os mesmos nomes existem no projeto Go: o harness chama estes
# alvos dentro da imagem de checks dele, com o ambiente (DB_*, APP_KEY, pepper) já definido.
PHP ?= php
COMPOSER ?= composer
PORT ?= 8080

.PHONY: up down migrate seed run test coverage lint arch audit

up:
	docker compose up -d --build

down:
	docker compose down

migrate:
	$(PHP) artisan migrate --force

seed:
	$(PHP) artisan db:seed --force

# Servidor embutido com workers: o mesmo para todas as células da stack.
run:
	PHP_CLI_SERVER_WORKERS=4 $(PHP) artisan serve --host=0.0.0.0 --port=$(PORT) --no-reload

test:
	$(PHP) vendor/bin/phpunit

coverage:
	mkdir -p build
	$(PHP) vendor/bin/phpunit --coverage-cobertura build/coverage.xml --coverage-text --only-summary-for-coverage-text

lint:
	$(PHP) vendor/bin/pint --test
	$(PHP) vendor/bin/phpstan analyse --no-progress --memory-limit=1G

arch:
	$(PHP) vendor/bin/deptrac analyse --no-progress

audit:
	$(COMPOSER) audit --locked
