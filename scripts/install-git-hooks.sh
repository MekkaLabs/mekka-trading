#!/usr/bin/env bash
#
# install-git-hooks.sh — instala hooks customizados deste repo
# ============================================================
#
# Instala (com symlink) os hooks de scripts/git-hooks/ em .git/hooks/.
# Idempotente: re-rodar não duplica.
#
# Hooks instalados:
#   - pre-commit-obsidian → .git/hooks/pre-commit
#   - pre-push-imp-sync   → .git/hooks/pre-push
#
# Desinstalar:
#   rm .git/hooks/pre-commit .git/hooks/pre-push

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
SOURCE_DIR="$REPO_ROOT/scripts/git-hooks"

install_hook() {
    local source_file="$1"
    local target_name="$2"
    local source_path="$SOURCE_DIR/$source_file"
    local target_path="$HOOKS_DIR/$target_name"

    if [[ ! -f "$source_path" ]]; then
        echo "❌ source não existe: $source_path"
        return 1
    fi

    if [[ -e "$target_path" && ! -L "$target_path" ]]; then
        echo "⚠️  $target_path existe e não é symlink — backup criado"
        mv "$target_path" "${target_path}.backup-$(date +%Y%m%d-%H%M%S)"
    fi

    ln -sfn "$source_path" "$target_path"
    chmod +x "$source_path"
    echo "✓ instalado: $target_name → $source_file"
}

mkdir -p "$HOOKS_DIR"

install_hook "pre-commit-obsidian" "pre-commit"
install_hook "pre-push-imp-sync" "pre-push"

echo ""
echo "Hooks instalados em $HOOKS_DIR"
echo "Para desinstalar: rm $HOOKS_DIR/pre-commit $HOOKS_DIR/pre-push"
echo "Para bypass: SKIP_OBSIDIAN_HOOK=1 git commit  |  SKIP_IMP_SYNC=1 git push"
