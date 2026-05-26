# Second Brain — Mekka Trading

Vault Obsidian canônico (uso diário):

- `~/Documents/mekka-trading-obsidian`

Backup pré-migração (não tocar):

- `~/Documents/mekka-trading-obsidian.backup-20260526-162005`

Fonte versionada (parte do segundo cérebro que vive no repo):

- `docs/obsidian/`

## Entradas recomendadas (no vault)

- `Home.md` — dashboard PARA + estado atual
- `30 - Resources/Fontes de Verdade.md` — política de SoT
- `30 - Resources/Guia de Manutenção do Segundo Cérebro.md` — manual operacional
- `30 - Resources/Instruções para Claude Code.md` — guidance para sessões AI
- `30 - Resources/Migração do Segundo Cérebro - 2026-05-26.md` — histórico
- `10 - Projects/Mekka Trading/Projeto - Mekka Trading.md` — projeto ativo

## Ciclo de sincronização

```
docs/obsidian/  ── scripts/obsidian_sync.py ──▶  ~/Documents/mekka-trading-obsidian/
       ▲                                                       │
       └──── promoção manual ◀── notas estáveis do vault ──────┘
```

## Comandos essenciais

```bash
# Diagnóstico: o que sincronizaria?
python scripts/obsidian_sync.py

# Aplicar arquivos novos (seguro — sem overwrite)
python scripts/obsidian_sync.py --apply

# Aplicar + resolver conflitos com backup
python scripts/obsidian_sync.py --apply --update

# Auditoria de cobertura código ↔ notas
python scripts/obsidian_coverage_audit.py
```

Detalhes completos em `docs/obsidian/30 - Resources/Guia de Manutenção do Segundo Cérebro.md`.
