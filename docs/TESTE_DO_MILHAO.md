# Teste do Milhão — Checklist de Resiliência Mekka Trading

> **Regra inviolável:** se você não responde TODAS com confiança, o sistema NÃO está pronto para banca real.
>
> Responda honestamente antes de qualquer mudança em produção ou migração para capital real.
> Registre data, versão do commit e suas respostas. Revisar a cada release significativo.

---

## Como usar

1. Responda cada pergunta com `SIM` / `NÃO` / `PARCIALMENTE`
2. Para `NÃO` ou `PARCIALMENTE` → crie issue ou story antes de ir a real
3. Assine com commit SHA + data no final
4. Armazene no Obsidian em `60 - Análises Externas/Teste-do-Milhao-YYYY-MM-DD.md`

---

## Bloco 1 — Sobrevivência Autônoma

| # | Pergunta | Resposta | Observação |
|---|----------|----------|------------|
| 1.1 | O sistema sobrevive 24h sem nenhuma intervenção minha? | | |
| 1.2 | Se eu tirar férias por 1 semana, o sistema para de operar sozinho no limite de drawdown? | | |
| 1.3 | Existe alguém além de mim que sabe como desligar o sistema de emergência? | | |
| 1.4 | O kill switch funciona sem conexão com o LLM? | | |
| 1.5 | O kill switch funciona sem conexão com a exchange? | | |

---

## Bloco 2 — Falhas de Infraestrutura

| # | Pergunta | Resposta | Observação |
|---|----------|----------|------------|
| 2.1 | Se a exchange cair por 1h durante posição aberta, o que acontece? (descreva) | | |
| 2.2 | Se o servidor reiniciar no meio de uma ordem, o estado é recuperável sem intervenção? | | |
| 2.3 | Se o feed de preço travar com valor stale por 10 minutos, o sistema detecta e para? | | |
| 2.4 | Se a conexão WebSocket cair, o sistema reconecta automaticamente sem abrir ordens duplicadas? | | |
| 2.5 | Se o banco SQLite ficar corrompido, há backup ou WAL que permita recuperação? | | |
| 2.6 | Se a máquina perder energia durante um trade, a posição fica visível no próximo boot? | | |

---

## Bloco 3 — Falhas de LLM

| # | Pergunta | Resposta | Observação |
|---|----------|----------|------------|
| 3.1 | Se o LLM provider ficar indisponível por 4h, qual o comportamento exato do sistema? | | |
| 3.2 | Se o LLM alucinar e retornar JSON inválido 10 vezes seguidas, o sistema para ou continua? | | |
| 3.3 | Se o LLM retornar sempre LONG com 0.99 confidence (prompt injection), o Batman bloqueia? | | |
| 3.4 | Se o custo de API ultrapassar $50/dia por bug de loop, há algum protetor? | | |
| 3.5 | O sistema entra em DEGRADED_MODE (sem novas entradas) quando o LLM falha repetidamente? | | |
| 3.6 | Prompts versionados? É possível reproduzir exatamente qual prompt gerou qual decisão? | | |

---

## Bloco 4 — Risco Financeiro

| # | Pergunta | Resposta | Observação |
|---|----------|----------|------------|
| 4.1 | Qual a perda máxima possível em 1 dia? (valor USD exato) | | |
| 4.2 | Qual a perda máxima possível em 1 semana sem intervenção? | | |
| 4.3 | Se 3 trades simultâneos forem LONG no mesmo ativo, o sistema detecta correlação? | | |
| 4.4 | O sistema fecha posições automaticamente em caso de drawdown máximo? | | |
| 4.5 | Existe proteção contra circuit breaker da bolsa (halt de mercado)? | | |
| 4.6 | O tamanho de posição está hardcapped independente do que o LLM retornar? | | |
| 4.7 | Em alavancagem máxima, qual o pior caso de liquidação? Está dentro do tolerável? | | |

---

## Bloco 5 — Observabilidade e Auditoria

| # | Pergunta | Resposta | Observação |
|---|----------|----------|------------|
| 5.1 | É possível reconstruir 100% do que aconteceu ontem a partir dos logs? | | |
| 5.2 | Cada decisão de trade está ligada ao snapshot de mercado que a gerou? | | |
| 5.3 | É possível reproduzir uma decisão passada em backtest com inputs idênticos? | | |
| 5.4 | Alertas críticos chegam no Telegram em < 60 segundos? | | |
| 5.5 | Existe alerta se o sistema ficar SILENCIOSO por mais de 2× o intervalo normal? | | |
| 5.6 | O custo de API é monitorado e alertado quando ultrapassa threshold diário? | | |

---

## Bloco 6 — Chaos Engineering (teste manual)

Execute estes testes **antes de cada migração para real** e registre o resultado:

| # | Teste | Procedimento | Resultado esperado | Data/Resultado |
|---|-------|--------------|-------------------|----------------|
| 6.1 | Matar LLM | Bloquear acesso à API OpenAI (firewall/hosts) | Sistema entra em DEGRADED_MODE, nenhuma nova entrada | |
| 6.2 | Matar exchange | Bloquear acesso Hyperliquid | Sistema pausa ordens, mantém posições, alerta Telegram | |
| 6.3 | Preço stale | Injetar preço congelado no feed | Sistema detecta em ≤ N minutos, emite alerta | |
| 6.4 | Restart no meio de trade | Matar processo durante ciclo ativo | Estado recuperável, sem ordem duplicada | |
| 6.5 | LLM alucinando | Mockar LLM retornando JSON inválido 10x | Kill switch ou DEGRADED_MODE após threshold | |
| 6.6 | Drawdown forçado | Simular -10% drawdown via Deadpool | Trading para automaticamente | |
| 6.7 | Loop de custo | Ciclo acelerado sem rate limit | Custo diário dispara alerta antes de atingir cap | |

---

## Checklist de Gate Final (assinar antes de ir a real)

```
[ ] Todos os SIM/NÃO do Bloco 1–5 respondidos
[ ] Todos os NÃO convertidos em stories ou aceitos conscientemente como risco
[ ] Testes 6.1, 6.2, 6.4, 6.6 executados e aprovados
[ ] Perda máxima diária calculada e aceita (Bloco 4.1)
[ ] Alguém além de mim sabe desligar (Bloco 1.3)
[ ] Kill switch testado manualmente
[ ] Paper trading 30+ dias com config idêntica ao real
```

---

## Histórico de Revisões

| Data | Commit SHA | Responsável | Resultado |
|------|-----------|-------------|-----------|
| 2026-05-15 | (criação inicial) | Gusta | Primeira versão — NÃO validado para real |

---

*Documento criado em Story 137. Revisar a cada release major ou antes de qualquer migração para capital real.*
