# Imagem de checks do HARNESS para a stack PHP/Laravel. Nunca construída a partir do workspace:
# o código escrito pela LLM só é montado (somente leitura) e executado aqui dentro.
# Versões fixadas na data do congelamento (2026-10-07); atualizar = mudar o tratamento.
FROM php:8.5.11-cli

RUN apt-get update \
 && apt-get install -y --no-install-recommends git unzip make libpq-dev libzip-dev libicu-dev \
 && docker-php-ext-install pdo_pgsql zip intl bcmath \
 && pecl install pcov && docker-php-ext-enable pcov \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

# PHPMetrics em phar: ferramenta do HARNESS, isolada do vendor do projeto (acoplamento, LCOM,
# abstratividade e distância da sequência principal por namespace).
RUN curl -fsSL -o /opt/phpmetrics.phar \
      https://github.com/phpmetrics/PhpMetrics/releases/download/v2.11.0/phpmetrics.phar \
 && php /opt/phpmetrics.phar --version

ENV COMPOSER_ALLOW_SUPERUSER=1 \
    COMPOSER_NO_INTERACTION=1 \
    PCOV_ENABLED=1

WORKDIR /work
