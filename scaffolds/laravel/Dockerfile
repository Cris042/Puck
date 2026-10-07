FROM php:8.5.11-cli
RUN apt-get update && apt-get install -y --no-install-recommends git unzip make libpq-dev libzip-dev libicu-dev \
 && docker-php-ext-install pdo_pgsql zip intl bcmath && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer
WORKDIR /app
COPY composer.json composer.lock ./
RUN composer install --no-dev --no-scripts --no-autoloader --prefer-dist
COPY . .
RUN composer dump-autoload --optimize --no-dev
EXPOSE 8080
CMD ["sh", "-c", "make migrate && make run"]
