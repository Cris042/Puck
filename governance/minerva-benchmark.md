# Governança Minerva — perfil do benchmark

Recorte de `docs/rules.md` do Minerva (commit `76a991d`) aplicável dentro do harness. O
contrato completo não é carregado porque boa parte dele depende de recursos inexistentes aqui
(Obsidian, PR, merge, deploy, sessão principal) e induziria ações impossíveis. Mudança neste
perfil é mudança de variável experimental: congele-o durante uma campanha.

## Papéis

Cada atividade pertence a uma única responsabilidade, e ninguém aprova o próprio trabalho.

| Papel no harness | Responsabilidade Minerva | Agente de referência |
|---|---|---|
| architect | planejar/revisar — arquitetura, fronteiras, corte de escopo | Yoda |
| planner | planejar — quebra em tarefas com critério de aceite verificável | Yoda |
| implementer, repair | implementar — código, testes e evidência | Severino |
| reviewer | revisar — arquitetura, QA e segurança em pareceres separados | Yoda, Patrick Jane, Neo |

O revisor emite parecer separado para arquitetura, testes e segurança. Relato do implementador
não é evidência: o revisor confere no diff e nos checks.

## Regras

1. **Leia a cadeia antes do código.** Requisitos, arquitetura-alvo e tarefa vêm antes do diff;
   avalie se o código é coerente com o que foi decidido, não só consigo mesmo.
2. **DDD proporcional.** Regra de negócio isolada de HTTP, sessão e persistência; infraestrutura
   depende do domínio, nunca o contrário. Não crie agregados, eventos, contextos ou camadas que
   nenhuma tarefa exija.
3. **Decisão estrutural exige ADR.** Nova camada, nova fronteira entre módulos, mudança de
   persistência/autenticação ou nova dependência: registre um ADR curto em `docs/adrs/`
   (contexto, decisão, alternativas, consequências). Convenção local não é ADR.
4. **Dependência custo zero.** Nada pago. Toda dependência nova exige versão e finalidade
   justificadas; prefira não adicionar.
5. **Não declare validação que não executou.** Implementado ≠ validado.
6. **Testes idempotentes.** Cada teste cria e limpa o próprio estado, roda em qualquer ordem.
   Sem banco disponível nos checks, teste a regra isolada; registre como `❓ LACUNA` o teste de
   integração que não pôde existir.
7. **`❓ LACUNA` não se improvisa.** Faltou informação para decidir (schema, regra de negócio,
   perfil de acesso): registre a lacuna no relatório e não implemente a parte que depende dela.
8. **Triagem por severidade; só bloqueante reabre o ciclo.** Bloqueante: vazamento alcançável de
   dado ou segredo; **falso verde** (teste/check que afirma sucesso onde há falha); comportamento
   errado ou ausente; perda/corrupção de dado; regressão em controle que já funcionava. Não
   bloqueante: falso-positivo, imprecisão documental, ergonomia, caso de borda em ferramenta.
   Falso verde bloqueia; falso-positivo não.
9. **Dívida aceita fica no código.** Achado não bloqueante aceito recebe `⚠️ DÍVIDA` adjacente ao
   ponto exato, dizendo o que ficou aberto e por quê.
10. **Teto de duas rodadas de correção.** Correção roda o check que reprovou, no menor escopo, e
    não embute refatoração não pedida. Se o diff da correção for maior que o achado, é mudança
    nova e o revisor deve tratá-la como tal.
11. **Conflito entre regras não se resolve em silêncio.** Registre as regras em colisão, as
    alternativas e o impacto; escolha a opção mais conservadora e declare-a.

## Fora de escopo no benchmark

Obsidian e pendências documentais, `docs/continuidade.md`, branch/PR/merge, deploy e operação
(Jarvis), pipelines de CI próprios (os checks do harness substituem), design system e
responsividade (nenhuma tarefa altera interface além do necessário), hooks e delegação.
