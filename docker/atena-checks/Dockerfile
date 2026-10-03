# Ambiente determinístico dos checks do Atena.
# PHP 7.3 porque o composer.lock do Atena fixa mpdf/mpdf v8.0.0 (php ~7.3.0).
# Ferramentas ficam instaladas globalmente: a LLM não precisa (nem consegue) rodar composer install.
#
#   docker build -t atena-checks:php7.3 docker/atena-checks
FROM php:7.3-cli

ARG PHPUNIT_VERSION=9.6.22
ARG PHPSTAN_VERSION=1.12.12

ADD https://phar.phpunit.de/phpunit-${PHPUNIT_VERSION}.phar /usr/local/bin/phpunit
ADD https://github.com/phpstan/phpstan/releases/download/${PHPSTAN_VERSION}/phpstan.phar /usr/local/bin/phpstan
COPY bin/ /usr/local/bin/
RUN chmod 755 /usr/local/bin/phpunit /usr/local/bin/phpstan /usr/local/bin/atena-* \
 && docker-php-ext-install pdo_mysql

WORKDIR /app
