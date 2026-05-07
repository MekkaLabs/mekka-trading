# Contribuindo com Mekka Trading

Bem-vindo. Este guia descreve como trabalhar no projeto.

---

## 1. Fluxo Git (GitHub Flow simples)

```
main ──●──────●──────●──────●──── (sempre verde, sempre deploy-ready)
        \    /\    /\    /
         f1   f2    f3              feature branches curtas
```

### Regras

1. **`main`** é sempre estável e tem que passar todos os quality gates
2. Todo trabalho novo nasce em uma **branch a partir de `main`**
3. Branches têm vida curta — **fechar em 1 a 5 dias**
4. PR para `main` só é mergeada com:
   - Lint, typecheck, testes e build verdes
   - Pelo menos uma revisão (você mesmo, em projeto solo)
   - Descrição clara do "porquê"

### Nomeação de branches

```
<tipo>/<resumo-curto>

# Exemplos
feat/risk-regime-suppression
fix/replay-lock-deadlock
docs/obsidian-onboarding
chore/update-dependencies
refactor/squad-router
```

Tipos válidos: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `build`, `ci`.

---

## 2. Commits — Conventional Commits

Formato:

```
<tipo>(<escopo opcional>): <descrição em minúsculas, 50–72 chars>

[corpo opcional explicando o porquê]

[footer opcional: BREAKING CHANGE, Refs #N, Co-authored-by, etc.]
```

### Exemplos

```
feat(risk-engine): adiciona suppression window em alertas críticos
fix(observability): corrige race em replay lock sob alta concorrência
docs(obsidian): cria MOC de agentes e templates iniciais
chore(deps): bump typescript de 5.7.2 para 5.7.3
refactor(squad-router): extrai planner para módulo separado
test(execution-engine): cobre cenário de slippage extremo
```

### Tipos

| Tipo | Quando |
|---|---|
| `feat` | Nova funcionalidade |
| `fix` | Bug fix |
| `docs` | Apenas documentação |
| `style` | Formatação, sem mudança de código |
| `refactor` | Refatoração sem nova feature ou fix |
| `perf` | Melhoria de performance |
| `test` | Adição/ajuste de testes |
| `build` | Sistema de build, dependências |
| `ci` | Pipeline de CI |
| `chore` | Tarefas mecânicas/manutenção |

### Breaking changes

```
feat(risk-engine)!: remove modo legacy de kill-switch

BREAKING CHANGE: a flag --legacy-kill foi removida. Use --policy.
```

---

## 3. Versionamento — SemVer

Formato: `MAJOR.MINOR.PATCH` (ex: `0.1.0`).

| Bump | Quando |
|---|---|
| `MAJOR` | Breaking change na API pública |
| `MINOR` | Nova feature compatível |
| `PATCH` | Bug fix compatível |

Pré-release: `1.2.0-rc.1`, `1.2.0-beta.2`.

### Tags de release

```bash
git tag -a v0.2.0 -m "release v0.2.0 - <resumo>"
git push origin v0.2.0
```

Toda release tem entrada no `CHANGELOG.md`.

---

## 4. Pull Requests

### Template mental do PR

- **O que** — em uma frase
- **Por que** — contexto/motivação
- **Como** — escolhas de design relevantes
- **Riscos** — o que pode quebrar
- **Validação** — como você testou

### Checklist antes de merge

- [ ] `npm run lint` ✅
- [ ] `npm run typecheck` ✅
- [ ] `npm test` ✅
- [ ] `npm run build` ✅
- [ ] CHANGELOG atualizado se relevante
- [ ] Documentação no Obsidian atualizada se decisão arquitetural
- [ ] Sem `.env`, segredos, ou dados pessoais

---

## 5. Segurança

- **Nunca** commite `.env`, chaves privadas, tokens
- **Nunca** habilite trading real sem revisão formal de risco
- **Nunca** contorne `risk-engine` ou validation gates
- Se descobrir uma vulnerabilidade, abra uma issue privada

---

## 6. Documentação

- README é a porta de entrada
- ADRs vão em `docs/obsidian/30 - Resources/Decisoes Tecnicas/`
- Runbooks em `docs/obsidian/30 - Resources/Runbooks/`
- Aprendizados em `docs/obsidian/30 - Resources/` (com tag `#aprendizado`)
- Mudou arquitetura? Abre um ADR.
- Escreveu CLI nova? Documenta em runbook + atualiza README.

---

## 7. Estilo de código

- TypeScript: `strict: true` (já configurado em `tsconfig.json`)
- Python: black + ruff (sugerido)
- Testes: cada feature relevante deve vir com teste
- Prefira **código óbvio** a código clever

---

## 8. Antes de começar

Leia rapidamente:

- [`README.md`](./README.md) — visão geral
- [`AGENTS.md`](./AGENTS.md) — identidades dos agentes e hard rules
- [`docs/obsidian/Home.md`](./docs/obsidian/Home.md) — segundo cérebro
- [`docs/obsidian/50 - MOCs/MOC - Arquitetura.md`](./docs/obsidian/50%20-%20MOCs/MOC%20-%20Arquitetura.md)

Bem-vindo a bordo. 🚀
