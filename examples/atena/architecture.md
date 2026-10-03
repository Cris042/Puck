# Arquitetura-alvo do experimento

## Objetivo
Evoluir o monólito existente de forma incremental. O experimento não autoriza reescrita total sem justificativa.

## Restrições
- Continuar como monólito.
- Não introduzir microsserviços, filas, event sourcing, CQRS ou cache distribuído sem requisito explícito.
- PHP + MySQL continuam sendo a base tecnológica.
- Controllers tratam entrada/saída HTTP e delegam regra de negócio.
- Regra de negócio não deve depender diretamente de `$_POST`, `$_GET`, `$_FILES` ou HTML.
- Persistência deve ficar isolada da regra de negócio.
- SQL não deve ser criado dentro de Views.
- Dependências novas precisam de justificativa objetiva.
- Preferir mudanças incrementais, testáveis e reversíveis.
- Não criar abstrações especulativas para requisitos inexistentes.

## Princípio de simplicidade
A menor solução que satisfaz os requisitos, segurança e testabilidade é preferível a uma arquitetura mais sofisticada sem benefício mensurável.

## Ambiente de validação (contrato com o harness)
- Runtime de referência: **PHP 7.3** (o `composer.lock` fixa `mpdf/mpdf` v8.0.0, que exige `~7.3.0`).
  Código novo deve rodar em 7.3: sem tipos union, enums, `match`, propriedades readonly ou
  argumentos nomeados.
- Dependências de terceiros ficam em `Lib/vendor` (versionadas). Não há `composer install`
  durante o experimento: não adicione pacotes ao `composer.json` esperando que sejam instalados.
- Checks rodam em container sem rede e sem banco de dados. **PHPUnit 9.6** e **PHPStan 1.12**
  já estão disponíveis globalmente; não é preciso instalá-los.
- O check `phpunit` executa `phpunit.xml`/`phpunit.xml.dist` se existir, senão o diretório
  `tests/`. Testes precisam rodar sem MySQL: isole a regra testada de `MySql::conectar()`.
- O schema do banco não está no repositório. Qualquer suposição sobre tabelas e colunas deve ser
  registrada no relatório, e mudanças de schema entregues como migration SQL em
  `database/migrations/`.
- `Models/ajax/*.php` são endpoints HTTP acessados diretamente (fora do `Router`): na prática
  pertencem à borda HTTP, como os controllers.
