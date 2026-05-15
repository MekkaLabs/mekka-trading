#!/usr/bin/env bash
# =============================================================================
# Mekka Trading — Push to GitHub (MekkaLabs/mekka-trading privado)
# Usa GitHub CLI (gh). Se nao estiver logado, abre o navegador.
#
# Auto-detecta o usuario logado via 'gh api user'.
# Para forcar outro owner: REPO_OWNER=outroNome ./scripts/push-to-github.sh
#
# Uso:
#   chmod +x scripts/push-to-github.sh
#   ./scripts/push-to-github.sh
# =============================================================================

set -e

# Cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Padrao: auto-detectar do gh login. Pode override via env var.
REPO_OWNER="${REPO_OWNER:-}"
REPO_NAME="${REPO_NAME:-mekka-trading}"
REPO_VISIBILITY="${REPO_VISIBILITY:---private}"

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Mekka Trading — Push to GitHub${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""

# 0. Verificar diretório
if [ ! -f "package.json" ] || [ ! -d ".git" ]; then
    echo -e "${RED}❌ Rode este script da raiz do projeto Mekka-Trading${NC}"
    echo -e "   cd ~/Documents/Mekka-Trading"
    exit 1
fi

# 1. Verificar gh CLI
echo -e "${YELLOW}🔧 Verificando GitHub CLI (gh)...${NC}"
if ! command -v gh &> /dev/null; then
    echo -e "${RED}❌ gh nao esta instalado.${NC}"
    echo ""
    echo -e "${YELLOW}Instale com Homebrew:${NC}"
    echo -e "   ${GREEN}brew install gh${NC}"
    echo ""
    echo -e "${YELLOW}Ou via download:${NC}"
    echo -e "   ${GREEN}https://cli.github.com/${NC}"
    exit 1
fi
echo -e "${GREEN}   ✓ gh instalado: $(gh --version | head -1)${NC}"

# 2. Verificar login no gh
echo ""
echo -e "${YELLOW}🔐 Verificando autenticacao gh...${NC}"
if ! gh auth status &> /dev/null; then
    echo -e "${YELLOW}   Voce nao esta logado. Iniciando login...${NC}"
    echo ""
    gh auth login --web --git-protocol https
fi

# Auto-detectar usuario gh
GH_USER=$(gh api user --jq .login 2>/dev/null || echo "")
if [ -z "$GH_USER" ]; then
    echo -e "${RED}❌ Falha em obter usuario gh${NC}"
    exit 1
fi
echo -e "${GREEN}   ✓ Logado como: ${GH_USER}${NC}"

# 3. Definir REPO_OWNER se nao foi setado via env var
if [ -z "$REPO_OWNER" ]; then
    REPO_OWNER="$GH_USER"
fi
REPO_FULL="${REPO_OWNER}/${REPO_NAME}"

echo ""
echo -e "${YELLOW}📍 Reposiorio destino: ${BLUE}${REPO_FULL}${YELLOW} (${REPO_VISIBILITY/--/})${NC}"

# 4. Verificar acesso ao owner (so checar se for diferente do usuario logado)
if [ "$REPO_OWNER" != "$GH_USER" ]; then
    echo ""
    echo -e "${YELLOW}🏢 Verificando acesso a org/usuario '${REPO_OWNER}'...${NC}"
    if ! gh api "users/${REPO_OWNER}" &> /dev/null && ! gh api "orgs/${REPO_OWNER}" &> /dev/null; then
        echo -e "${RED}❌ '${REPO_OWNER}' nao existe no GitHub.${NC}"
        echo ""
        echo -e "${YELLOW}Para usar sua conta pessoal (${GH_USER}), rode sem REPO_OWNER:${NC}"
        echo -e "   ${GREEN}./scripts/push-to-github.sh${NC}"
        echo ""
        echo -e "${YELLOW}Para usar outra org existente:${NC}"
        echo -e "   ${GREEN}REPO_OWNER=NomeDaOrg ./scripts/push-to-github.sh${NC}"
        exit 1
    fi
    echo -e "${GREEN}   ✓ '${REPO_OWNER}' acessivel${NC}"
fi

# 4. Verificar se o repo já existe
echo ""
echo -e "${YELLOW}📦 Verificando se ${REPO_FULL} ja existe...${NC}"
if gh repo view "${REPO_FULL}" &> /dev/null; then
    echo -e "${YELLOW}   ⚠️  Repositorio ja existe.${NC}"
    read -p "   Deseja apenas conectar e fazer push? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${RED}   Cancelado.${NC}"
        exit 1
    fi
    SKIP_CREATE=true
else
    SKIP_CREATE=false
    echo -e "${GREEN}   ✓ Nome disponivel${NC}"
fi

# 5. Criar repo (se nao existe)
if [ "$SKIP_CREATE" = false ]; then
    echo ""
    echo -e "${YELLOW}🚀 Criando ${REPO_FULL} (${REPO_VISIBILITY})...${NC}"
    gh repo create "${REPO_FULL}" \
        ${REPO_VISIBILITY} \
        --description "AI-Orchestrated Autonomous Trading Operating System (Megazord v1.1) — paper-only, risk-first, multi-agent" \
        --source=. \
        --remote=origin \
        --push=false
    echo -e "${GREEN}   ✓ Repositorio criado${NC}"
fi

# 6. Configurar remote (se ainda nao existe)
echo ""
echo -e "${YELLOW}🔗 Configurando remote origin...${NC}"
if git remote get-url origin &> /dev/null; then
    CURRENT_REMOTE=$(git remote get-url origin)
    echo -e "${YELLOW}   Remote ja configurado: ${CURRENT_REMOTE}${NC}"
    EXPECTED_REMOTE="https://github.com/${REPO_FULL}.git"
    if [ "$CURRENT_REMOTE" != "$EXPECTED_REMOTE" ]; then
        echo -e "${YELLOW}   Atualizando para: ${EXPECTED_REMOTE}${NC}"
        git remote set-url origin "$EXPECTED_REMOTE"
    fi
else
    git remote add origin "https://github.com/${REPO_FULL}.git"
    echo -e "${GREEN}   ✓ Remote adicionado${NC}"
fi

# 7. Push branch main + tags
echo ""
echo -e "${YELLOW}📤 Push da branch main + tags...${NC}"
git push -u origin main
git push origin --tags
echo -e "${GREEN}   ✓ Push completo${NC}"

# 8. Resumo
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Tudo no ar!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}📍 Repositorio:${NC} https://github.com/${REPO_FULL}"
echo -e "${YELLOW}📍 Branch:${NC}      main"
echo -e "${YELLOW}📍 Commits:${NC}     $(git rev-list --count HEAD)"
echo -e "${YELLOW}📍 Tags:${NC}        $(git tag | tr '\n' ' ')"
echo ""
echo -e "${BLUE}Proximos passos:${NC}"
echo "  1. Abrir o repo:        gh repo view --web"
echo "  2. Criar primeira PR:   git checkout -b feat/sua-feature"
echo "  3. Adicionar collabs:   gh repo edit --add-topic trading,ai,multi-agent"
echo ""
