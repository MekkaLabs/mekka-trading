#!/usr/bin/env bash
set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Erro: rode dentro de um repositório git."
  exit 1
fi

echo "== Arquivos alterados (git status) =="
git status --short

echo
echo "== Sugestão de atualização no segundo cérebro =="

affected=$(git status --porcelain | awk '{print $2}')

if [ -z "${affected}" ]; then
  echo "Nenhuma alteração pendente."
  exit 0
fi

for f in ${affected}; do
  case "$f" in
    *README*|*ARCHITECTURE*|*AGENTS*|*DEPLOY*)
      echo "- Atualizar Overview/Architecture/References por causa de: $f"
      ;;
    docs/stories/*|*story-*.md)
      echo "- Atualizar Stories/Roadmap por causa de: $f"
      ;;
    src/app/api/*|apps/api/*|api/*)
      echo "- Atualizar Modules + Operations (APIs) por causa de: $f"
      ;;
    src/app/*|apps/mobile/*|src/components/*)
      echo "- Atualizar Modules (UI/UX) por causa de: $f"
      ;;
    prisma/*|supabase/*|*schema*)
      echo "- Atualizar Architecture + Operations (dados/migrations) por causa de: $f"
      ;;
    scripts/*)
      echo "- Atualizar Operations/Runbooks por causa de: $f"
      ;;
    *)
      echo "- Revisar se precisa nota no segundo cérebro: $f"
      ;;
  esac
done
