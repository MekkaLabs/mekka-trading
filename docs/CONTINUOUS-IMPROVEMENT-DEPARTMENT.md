# Departamento de Melhoria Contínua — Design

> Visão: a área de Melhorias deixa de ser "o Beast olha trades" e vira um
> **departamento de melhoria contínua** que melhora **tudo** no projeto —
> agentes de trade, frontend, backend, infra, memória/segundo cérebro — e
> busca conhecimento **fora** do sistema (o próprio repositório/GitHub, a
> internet e bases de conhecimento de trading). Sempre com humano no controle
> (aprovar/reprovar) e guard-rails de segurança (sistema com dinheiro real).

---

## 1. O que acontece HOJE quando você clica "Buscar melhorias agora"

`GET /api/improvements?fresh=1` → `Mekka.run(period_days=7)`:

1. **Beast** (analista read-only, `src/agents/beast.py`) varre **4 fontes** dos
   últimos 7 dias e aplica regras de threshold para gerar propostas
   (`ImprovementProposal`: title, description, impact HIGH/MEDIUM/LOW, area,
   evidence, suggested_story):
   - **Trades fechados** — win rate, profit factor, avg win/loss, por símbolo.
   - **Gates do Batman** — qual gate mais rejeita (fricção de execução).
   - **Latência** — p95 por etapa/agente (eventos com duração).
   - **Qualidade de sinal** — win rate de alta vs baixa confiança.
2. **Inbox curado** (`data/improvement_inbox.json`) — propostas manuais de
   qualquer domínio (dev/front/back/infra), injetadas junto.
3. **Galactus** (premortem, `src/agents/galactus.py`) — para cada proposta
   calcula um **hunger score 0-100** = peso de impacto + criticidade da área +
   gap de evidência; lista failure modes + mitigações; **veredito**:
   `DEVOURED` (área crítica sem evidência), `NEEDS_HARDENING` (hunger ≥45/70),
   `SURVIVES`.
4. **Mekka** (comandante, `src/agents/mekka.py`) — consolida Beast + inbox,
   anexa o premortem do Galactus, aplica a decisão persistida do operador
   (accepted/rejected/pending), ranqueia (pendentes primeiro → prioridade →
   hunger) e devolve o `MekkaCouncilReport` (recommendations + summary).
5. Dashboard renderiza (kanban + lista + abas de status) e faz push das novas
   pendentes ao **Telegram** (aprovável por lá com `/aprovar`).

### Papel da Jean Grey hoje
`src/agents/jean_grey.py` — **Memory Master**. Audita o **vault (segundo
cérebro)**: links quebrados, notas órfãs, duplicatas, e expõe o **grafo neural**
(`build_graph` → `/api/jean/graph`). **Hoje ela NÃO gera propostas** para o
conselho — só dá saúde de memória. (Ver expansão na §4.)

### Limitações atuais (por que não é "uma empresa de melhoria contínua")
- Só enxerga **runtime de trade** (trades/gates/latência/sinais). Não audita
  **código** (front/back), **erros/logs**, **eventos de risco**, nem **memória**.
- Propostas de **dev** só vêm do **inbox manual** — nada é auto-detectado.
- **Nenhuma fonte externa** (repo/GitHub, internet, bases de trading).
- Sem **loop de medição**: não compara baseline antes/depois de uma entrega.

---

## 2. Arquitetura-alvo — "Scanners → Premortem → Consolidação → Operador → Dev → Medição"

```
        ┌─────────────────────── SCANNERS (read-only, por domínio) ───────────────────────┐
        │ Beast(trade runtime)  CodeAuditor(front/back)  RiskScanner(kill/drawdown)        │
        │ MemoryScanner(JeanGrey: vault+padrões)  OpsScanner(erros/logs)                   │
        │ ExternalResearcher(GitHub/web/bases de trading)                                  │
        └───────────────────────────────────────┬──────────────────────────────────────────┘
                                                 │  propostas {title,area,impact,evidence,domain,source}
                                                 ▼
                                  Galactus (premortem: hunger + failure modes)
                                                 ▼
                                  Mekka (consolida + ranqueia + decisão persistida)
                                                 ▼
                         Dashboard /Melhorias  +  Telegram   (operador aprova/reprova)
                                                 ▼
                         Fila docs/improvement-queue/  →  Claude Code (SDC) implementa
                                                 ▼
                         PR → operador aprova → Entregue  →  **Medição de impacto** (baseline antes/depois)
```

**Princípio que se mantém:** todo scanner é **read-only** e **fail-silent**;
nada executa sozinho; humano aprova; nunca toca arquivos de segurança
(`settings.py` double-gate, kill switch) — protegido por L1-L4 + deny rules.

---

## 3. Novos agentes/scanners (por domínio)

Todos herdam o padrão do Beast: read-only, evidence-based, devolvem
`list[ImprovementProposal]` para o Mekka consolidar; nunca lançam exceção.

| Agente (proposto) | Domínio | O que analisa | Fontes |
|---|---|---|---|
| **Beast** (existe) | trading-ops | trades, gates, latência, qualidade de sinal | DB de trades/eventos |
| **CodeAuditor** (novo) | dev-squad | arquivos grandes, complexidade, TODO/FIXME, cobertura de testes ausente, `ruff`/`mypy` findings, imports/ciclos | repo (Read/Grep/Glob, `ruff`, `mypy`, code-intel) |
| **OpsScanner** (novo) | dev-squad/infra | exceptions/erros recorrentes em logs e no audit stream, endpoints lentos, falhas de agente | `/tmp/mekka_dashboard.log`, `MekkaRepository` events |
| **RiskScanner** (novo) | trading-ops | frequência de kill switch, drawdown diário, exposição/concentração, rejeições do Batman por motivo | events + risk panel |
| **MemoryScanner** (Jean Grey expandida) | memory | vault: links quebrados/órfãs/duplicatas → propostas; **padrões de decisão** (DecisionMemory): erros repetidos que a memória já "sabe" | vault + working/episodic memory |
| **ExternalResearcher** (novo) | research | melhores práticas, libs, papers e técnicas de trading; mudanças de API das exchanges; CVEs de dependências | **WebSearch/WebFetch**, GitHub (releases/issues), docs |

### CodeAuditor — detalhe (gera as propostas dev que hoje vêm do inbox manual)
- Lê o repo (Read/Glob/Grep). Sinais: arquivos > N linhas (ex.: `server.py`
  6k → "refatorar"), `TODO/FIXME`, funções longas, ausência de teste para um
  módulo novo, `ruff`/`mypy` com findings, dependências desatualizadas.
- Cada achado vira `ImprovementProposal(area="backend"|"frontend", evidence=...)`.
- **Foi exatamente assim que "Refatorar server.py" deveria ter nascido** — hoje
  veio do inbox manual; o CodeAuditor o detectaria sozinho.

### ExternalResearcher — detalhe (o "buscar fora")
- **Repo/GitHub:** changelog de libs (pandas-ta, ccxt, aiohttp, pydantic),
  issues/PRs relevantes, releases com breaking changes/segurança.
- **Internet (WebSearch/WebFetch):** técnicas de trading (gestão de risco,
  regimes de vol, execução), benchmarks, *best practices* aplicáveis ao stack.
- **Bases de trading:** funding/curvas/derivativos (já temos MCPs financeiros
  disponíveis — LSEG, bigdata, etc.) para sugerir features de sinal.
- Guard-rail: pesquisa **read-only**; toda sugestão entra como proposta para o
  operador decidir (nunca aplica nada da internet automaticamente).

---

## 4. Loop de medição (fechar o ciclo "de empresa")
- Ao **entregar** uma melhoria, capturar **baseline** da métrica-alvo
  (ex.: win rate, p95, nº de erros/dia, linhas do arquivo).
- Após X dias, o conselho **compara antes/depois** e marca a melhoria como
  *efetiva* / *neutra* / *regressão* — alimentando a memória (Jean Grey) para
  não repetir o que não funcionou. Isso vira um KPI do departamento.

---

## 5. Plano de implementação (faseado — para o próximo chat, via SDC do AIOS)
1. **CodeAuditor** (maior valor imediato: auto-detecta dívidas dev). Novo
   `src/agents/code_auditor.py`; Mekka passa a chamá-lo junto do Beast.
2. **RiskScanner** + **OpsScanner** (segurança/estabilidade). Reusam events/logs.
3. **Jean Grey → MemoryScanner**: ela passa a propor (não só auditar).
4. **ExternalResearcher** (WebSearch/WebFetch + MCPs financeiros + GitHub).
5. **Loop de medição** + KPI do departamento no dashboard.
6. UI: filtrar propostas por **fonte/scanner**; aba "Pesquisa externa".

Cada fase: novo scanner read-only → Mekka consolida → testar boot/endpoint →
commit. Sem auto-merge; sem tocar safety gates.

---

## 6. Onde mexer (mapa rápido)
- Geração: `src/agents/{beast,galactus,mekka,jean_grey}.py` (+ novos scanners).
- Orquestração: `Mekka._beast_proposals` → generalizar para `_scanner_proposals`
  agregando todos os scanners.
- API: `/api/improvements[?fresh=1]`, `/api/improvements/pr-status`,
  `/api/improvements/approve-pr` (em `src/dashboard/server.py`).
- Fila/PR: `src/services/{improvement_queue,pr_tracker}.py`.
- UI: `src/dashboard/static/{app.js,index.html,style.css}` (kanban, abas, scan).
