# Mekka Trading — Cleanup Notes

Inventário de arquivos e diretórios que **podem ser removidos com
segurança** do repositório, mas que ainda estão lá por inércia. Cada
item tem comando exato e justificativa.

> **Regra de ouro**: **não** rode `rm -rf` em massa. Vá item por item,
> faça `ls` antes para confirmar conteúdo, e considere mover para uma
> pasta `~/.archive/mekka-trading-cleanup-YYYY-MM-DD/` em vez de
> deletar diretamente.

---

## Tier 1 — Lixo claro do git (5 pastas)

Pastas geradas por operações de git interrompidas (`git mv`, `git
clone --recurse-submodules`, etc.). Contêm o esqueleto de um repo git
(`HEAD`, `branches`, `config`) sem objetos válidos.

```
_git-stale-tmp/
_git-stale-tmp-1778180618/
_git-stale-tmp-1778180631/
_git-broken-tmp/
_git-broken-tmp2/
```

**Verificação antes de remover:**

```bash
cd /Users/gustavovicente/Documents/Mekka-Trading
for d in _git-stale-tmp _git-stale-tmp-1778180618 _git-stale-tmp-1778180631 _git-broken-tmp _git-broken-tmp2; do
  echo "--- $d ---"
  ls "$d" 2>/dev/null | head -5
  du -sh "$d" 2>/dev/null
done
```

**Remoção (se confirmou que não tem nada importante):**

```bash
mkdir -p ~/.archive/mekka-cleanup-$(date +%Y%m%d)
mv _git-stale-tmp _git-stale-tmp-* _git-broken-tmp _git-broken-tmp2 \
   ~/.archive/mekka-cleanup-$(date +%Y%m%d)/
```

**Risco de remoção**: zero. São restos de git transient.

## Tier 2 — Backups antigos

### `squads.zip` (3.2 MB)

Backup zip dos squads na raiz. O conteúdo já está extraído em
`squads/`. Mantém-se apenas como redundância.

```bash
ls -lh squads.zip
unzip -l squads.zip | head -20    # confere conteúdo
```

```bash
mv squads.zip ~/.archive/mekka-cleanup-$(date +%Y%m%d)/
```

**Risco**: baixo. `squads/` está populado e versionado em git.

### `_aiox-core-clone-tmp/`

Pasta deixada por uma operação anterior de clone do AIOX Core. O
framework "real" está em `aiox-core/`. Esta tmp é cópia temporária.

```bash
ls _aiox-core-clone-tmp/ | head
diff -rq _aiox-core-clone-tmp/ aiox-core/ 2>&1 | head -20
```

```bash
mv _aiox-core-clone-tmp ~/.archive/mekka-cleanup-$(date +%Y%m%d)/
```

**Risco**: baixo. Se for cópia idêntica, irrelevante. Se houver
divergência, archive primeiro, decida depois.

## Tier 3 — `.DS_Store` (macOS)

Arquivos espalhados em várias pastas (`./.DS_Store`, `docs/.DS_Store`,
etc.). Já estão no `.gitignore`, mas alguns podem ter escapado em
commits antigos.

```bash
find . -name ".DS_Store" -not -path "./.venv/*" -not -path "./node_modules/*" -not -path "./aiox-core/*"
```

```bash
find . -name ".DS_Store" -not -path "./.venv/*" -not -path "./node_modules/*" -not -path "./aiox-core/*" -delete
```

**Risco**: zero. Metadata de macOS, sem valor para o projeto.

## Tier 4 — `__pycache__/` órfãos

Bytecode Python compilado por Python 3.14. Quando o venv for trocado
para 3.13, esses cache irão recompilar para 3.13 — limpar antes evita
ambiguidade.

```bash
find . -type d -name "__pycache__" -not -path "./.venv/*" -not -path "./aiox-core/*"
find . -type d -name "__pycache__" -not -path "./.venv/*" -not -path "./aiox-core/*" -exec rm -rf {} +
```

**Risco**: zero. Recompila no próximo `pytest` ou `python run.py`.

---

## O que NÃO remover

Mesmo que pareça lixo, **NUNCA** remover sem revisão humana:

- `aiox-core/` — framework AIOX Core embutido. Pode ser submódulo.
- `.git/` — óbvio.
- `.venv/` — venv ativo do projeto.
- `node_modules/` — só se for re-rodar `npm install`.
- `dist/` — build TypeScript output. Usado em runtime via `node dist/cli/main.js`.
- `memory/*.ndjson` — audit log do Megazord (TS). É histórico operacional.
- `data/mekka_trading.db` — SQLite do Python. É histórico de signals/trades.
- `.pytest_cache/` — útil para acelerar reruns.

## Comando one-shot recomendado

Se você confirmou tudo acima e quer limpar de uma só vez:

```bash
cd /Users/gustavovicente/Documents/Mekka-Trading
ARCHIVE_DIR=~/.archive/mekka-cleanup-$(date +%Y%m%d-%H%M%S)
mkdir -p "$ARCHIVE_DIR"

# Tier 1 + 2: archive (safe)
mv _git-stale-tmp _git-stale-tmp-* _git-broken-tmp _git-broken-tmp2 \
   _aiox-core-clone-tmp squads.zip "$ARCHIVE_DIR/" 2>/dev/null

# Tier 3 + 4: delete in place (zero risk)
find . -name ".DS_Store" \
  -not -path "./.venv/*" -not -path "./node_modules/*" -not -path "./aiox-core/*" \
  -delete
find . -type d -name "__pycache__" \
  -not -path "./.venv/*" -not -path "./aiox-core/*" \
  -exec rm -rf {} + 2>/dev/null

echo "Archived to: $ARCHIVE_DIR"
git status
```

Depois rode `pytest -v` e `npm test` para confirmar que nada quebrou.

## Manutenção contínua

Para evitar acumular esses arquivos no futuro:

- Verifique `.gitignore` cobre `_git-*-tmp/`, `*.zip` na raiz,
  `__pycache__/`, `.DS_Store`. (Hoje cobre `.DS_Store` e
  `__pycache__/`.)
- Adicionar entrada `_git-*-tmp/` e `_aiox-core-clone-tmp/` ao
  `.gitignore` para nunca commitar de novo.
- Revisar este arquivo a cada milestone para detectar novo lixo.
