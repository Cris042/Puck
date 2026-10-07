# Atena legado executável, só para gerar o dataset dourado (fora da campanha, fora do workspace).
# PHP 7.3 é o runtime do commit fixado (composer.lock: mpdf exige ~7.3.0). O código entra montado,
# sem modificação: config.php aponta para `localhost`, então o MariaDB é alcançado pelo socket.
FROM php:7.3-apache
RUN docker-php-ext-install pdo_mysql && a2enmod rewrite \
 && printf 'pdo_mysql.default_socket=/run/mysqld/mysqld.sock\ndisplay_errors=Off\nlog_errors=On\n' \
    > /usr/local/etc/php/conf.d/legado.ini
