# Política de Segurança

## Hard Rules

- **Trading real bloqueado** na camada de risco (`PAPER_TRADING=true` é o default)
- **Kill switch** disponível e sob controle de governança
- **Hyperliquid mock-only** neste estágio
- Nenhuma chave de API ou roteamento de ordem real é implementado
- Nenhum compartilhamento de estado entre projetos
- Eventos, logs e audit-trail emitidos em **todas** as operações sensíveis

## Manuseio de Segredos

- **NUNCA** commitar `.env`
- Use `.env.example` como referência
- Rotação periódica de chaves (Hyperliquid, OpenAI, Telegram, CryptoPanic)
- Em caso de exposição acidental: revogar, rotacionar e registrar incidente

## Reportando Vulnerabilidades

Em projeto privado, abra uma issue marcada como **Security** com label confidencial, ou contate o maintainer diretamente.

**NÃO** abra discussão pública antes de remediar.

## Escopo

Esta política cobre:
- Código deste repositório
- Configurações default
- Documentação que possa induzir uso inseguro

NÃO cobre:
- Dependências de terceiros (reportar ao upstream)
- Chaves do usuário (responsabilidade individual)
