#!/usr/bin/env bash
# =============================================================================
# Mekka Trading — Bootstrap Git
# Inicializa o repositório com commits semânticos organizados em camadas.
# Rode UMA VEZ no diretório raiz do projeto.
#
# Uso:
#   chmod +x scripts/bootstrap-git.sh
#   ./scripts/bootstrap-git.sh
# =============================================================================

set -e  # parar em qualquer erro

# Cores para o output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Mekka Trading — Bootstrap Git${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""

# 0. Verificar diretório
if [ ! -f "package.json" ] || [ ! -f "README.md" ]; then
    echo -e "${RED}❌ Rode este script da raiz do projeto Mekka-Trading${NC}"
    exit 1
fi

# 1. Limpar artefatos do bootstrap (se houver)
echo -e "${YELLOW}🧹 Limpando artefatos do bootstrap...${NC}"
rm -rf _git-broken-tmp _git-broken-tmp2 _aiox-core-clone-tmp 2>/dev/null || true
rm -rf .git 2>/dev/null || true
echo -e "${GREEN}   ✓ artefatos removidos${NC}"

# 2. git init
echo ""
echo -e "${YELLOW}📦 Inicializando repositório Git...${NC}"
git init -b main
git config user.name "Gusta"
git config user.email "gustav0.v1c3nt3@gmail.com"
echo -e "${GREEN}   ✓ git inicializado em branch 'main'${NC}"

# 3. Commit em camadas semânticas
echo ""
echo -e "${YELLOW}📝 Criando commits semânticos em camadas...${NC}"

# --- Camada 1: governança ---
git add .gitignore .gitattributes README.md CHANGELOG.md CONTRIBUTING.md SECURITY.md AGENTS.md .github/ 2>/dev/null || true
git commit -m "chore: bootstrap project governance

- .gitignore (python + node + ide + secrets)
- .gitattributes (eol normalization + linguist)
- README.md atualizado com setup, CLIs e visão arquitetural
- CHANGELOG.md (Keep a Changelog) com release v0.1.0
- CONTRIBUTING.md (GitHub Flow + Conventional Commits + SemVer)
- SECURITY.md (hard rules + manuseio de segredos)
- AGENTS.md preservado (identidades dos agentes)
- .github/ com PR template e issue templates"
echo -e "${GREEN}   ✓ commit 1: governança${NC}"

# --- Camada 2: configs ---
git add package.json package-lock.json tsconfig.json pyproject.toml requirements.txt conftest.py .env.example 2>/dev/null || true
git commit -m "chore: add project configuration files

- package.json + package-lock.json (Node deps + scripts)
- tsconfig.json (TypeScript strict mode)
- pyproject.toml + requirements.txt (Python config)
- conftest.py (pytest fixtures)
- .env.example (template — NUNCA commitar .env real)"
echo -e "${GREEN}   ✓ commit 2: configs${NC}"

# --- Camada 3: código TypeScript core ---
git add index.ts agents/ workflows/ prompts/ cli/ scripts/ 2>/dev/null || true
git commit -m "feat: add core TypeScript modules (agents, workflows, cli)

- agents/ — definições individuais de agentes
- workflows/ — workflows orquestrados
- prompts/ — prompts estruturados
- cli/ — CLIs operacionais (runtime, replay, ops, health, etc.)
- scripts/ — scripts auxiliares (lint, bootstrap)
- index.ts — entrypoint principal"
echo -e "${GREEN}   ✓ commit 3: core TS${NC}"

# --- Camada 4: domínio de trading ---
git add exchanges/ market-data/ risk-engine/ execution-engine/ strategy-engine/ backtesting/ 2>/dev/null || true
git commit -m "feat: add trading domain modules

- exchanges/hyperliquid/ — adaptador mock da Hyperliquid
- market-data/ — feeds de mercado
- risk-engine/ — políticas de risco + kill switch
- execution-engine/ — motor de execução paper-only
- strategy-engine/ — geração de sinais
- backtesting/ — replay e validação histórica"
echo -e "${GREEN}   ✓ commit 4: trading domain${NC}"

# --- Camada 5: observability + memory + squads ---
git add observability/ memory/ squads/ src/ run.py 2>/dev/null || true
git commit -m "feat: add observability, memory and squads infrastructure

- observability/ — store, alerts, reports (jsonl pipeline)
- memory/ — audit-log, alerts, reports persistidos
- squads/ — 14 squads especializadas (advisory, brand, c-level,
  claude-code-mastery, copy, cybersec, data, design, hormozi,
  movement, storytelling, traffic-masters)
- src/ — utilitários Python
- run.py — entrypoint Python auxiliar

Hard rules: paper-only, kill-switch, no real orders, audit-trail
emitido em todas as operações sensíveis." 2>/dev/null || true
echo -e "${GREEN}   ✓ commit 5: observability + squads${NC}"

# --- Camada 6: documentação Obsidian ---
git add docs/ 2>/dev/null || true
git commit -m "docs: add Obsidian second brain (PARA + MOC)

- Vault Obsidian em docs/obsidian/ com estrutura PARA:
  Inbox, Projects, Areas, Resources, Archive, MOCs, Daily,
  Templates, Attachments
- 6 MOCs iniciais: Arquitetura, Agentes IA, Trading,
  Risco & Compliance, Operações & Observability, Aprendizados
- Templates: ADR, Runbook, Aprendizado, Agente, Estratégia,
  Story, Daily Note
- ADR-001: adoção de PARA + MOC
- Runbook: iniciar runtime do Megazord
- Glossário do projeto
- 24 stories preservadas em docs/stories/

Workspace e cache do Obsidian ignorados via .gitignore."
echo -e "${GREEN}   ✓ commit 6: Obsidian docs${NC}"

# 4. Tag inicial
echo ""
echo -e "${YELLOW}🏷️  Criando tag v0.1.0...${NC}"
git tag -a v0.1.0 -m "v0.1.0 — Megazord v1.1 foundation

Primeira versão estável do Mekka Trading com:
- Mission planner + squad router + runtime loop
- Risk-first execution (paper-only)
- Observability completa (logs + eventos + audit)
- 24 stories implementadas
- 14 squads especializadas
- Documentação Obsidian (PARA + MOC)"
echo -e "${GREEN}   ✓ tag v0.1.0 criada${NC}"

# 5. Resumo
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Repositório local pronto!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}📊 Histórico:${NC}"
git log --oneline --decorate
echo ""
echo -e "${YELLOW}📈 Estatísticas:${NC}"
echo "   Total de commits: $(git rev-list --count HEAD)"
echo "   Total de arquivos rastreados: $(git ls-files | wc -l | tr -d ' ')"
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}📤 PRÓXIMOS PASSOS — criar repo no GitHub:${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "1) Crie um repositório PRIVADO em https://github.com/new"
echo "   Nome sugerido: Mekka-Trading"
echo "   ⚠️  NÃO inicialize com README/license/.gitignore (já temos tudo)"
echo ""
echo "2) Conecte o repositório local ao remoto:"
echo -e "${GREEN}   git remote add origin git@github.com:SEU_USUARIO/Mekka-Trading.git${NC}"
echo "   (use SSH se tiver chave configurada — recomendado)"
echo ""
echo "   ou via HTTPS:"
echo -e "${GREEN}   git remote add origin https://github.com/SEU_USUARIO/Mekka-Trading.git${NC}"
echo ""
echo "3) Suba o código + tags:"
echo -e "${GREEN}   git push -u origin main${NC}"
echo -e "${GREEN}   git push origin v0.1.0${NC}"
echo ""
echo "4) (Opcional) Adicionar aiox-core como SUBMÓDULO:"
echo -e "${GREEN}   # Primeiro remova a entrada do .gitignore que ignora aiox-core/${NC}"
echo -e "${GREEN}   # Depois rode:${NC}"
echo -e "${GREEN}   rm -rf aiox-core${NC}"
echo -e "${GREEN}   git submodule add https://github.com/SynkraAI/aiox-core.git aiox-core${NC}"
echo -e "${GREEN}   git commit -m \"chore: add aiox-core as submodule\"${NC}"
echo -e "${GREEN}   git push${NC}"
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}🔄 Workflow daily (GitHub Flow):${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "   git checkout -b feat/nome-da-feature"
echo "   # ...trabalhe..."
echo "   git add ."
echo "   git commit -m \"feat(escopo): descrição\""
echo "   git push -u origin feat/nome-da-feature"
echo "   # abra Pull Request no GitHub"
echo "   # após merge:"
echo "   git checkout main && git pull"
echo ""
echo -e "${GREEN}🚀 Bom trabalho!${NC}"
