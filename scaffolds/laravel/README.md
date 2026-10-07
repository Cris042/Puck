# Escola — esqueleto PHP/Laravel

Ponto de partida fixo das células PHP/Laravel do benchmark. Contém só a instalação oficial do
Laravel, a configuração para PostgreSQL, as ferramentas da base técnica (Pint, PHPStan + Larastan,
Deptrac, PHPUnit + pcov) e os alvos de `make`.

```bash
cp .env.example .env   # preencha APP_KEY (php artisan key:generate) e APP_PASSWORD_PEPPER
make up                # app + PostgreSQL em http://localhost:8080
make test lint arch coverage
```

`GET /saude` responde `{"status": "ok"}` quando a aplicação está no ar.
