---
rec_id: "office-full-noscroll"
status: queued
domain: "dev-squad"
area: "frontend"
priority: "P2"
created_at: "2026-05-20"
---

# IMP-office-full-noscroll — Office na Visão Geral sem barra de rolagem (exibir completo)

## Title

Exibir o office completo na Visão Geral, sem barra de rolagem.

## Context / Impact

- **Domain:** dev-squad
- **Area:** frontend
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** ACCEPT (pedido direto do operador)
- **Rationale:** Hoje, na Visão Geral, o office (iframe `#office-v2-frame`) fica
  com altura fixa dentro do grid `.overview-office-row` e gera barra de rolagem.
  O operador quer ver a cena inteira do escritório de uma vez, sem rolar.

## Description

Na Visão Geral, o office deve aparecer **completo** (toda a cena 560×300 +
header/rodapé do iframe) sem barra de rolagem vertical nem horizontal, mantendo
o layout lado-a-lado com o Trade Mode (`grid 2fr/1fr`).

Pontos a investigar/ajustar:
- `src/dashboard/static/style.css` — regra `.overview-office-row:not(.office-row-solo) #office-v2-frame`
  hoje fixa `height: 600px; max-height: 70vh` (e 480px no media ≤1100px), o que
  corta a cena e cria scroll. Ajustar para que o iframe acomode a cena inteira
  (ex.: usar `aspect-ratio` da cena 560/300, ou medir o conteúdo e setar altura
  dinâmica), com `overflow: hidden` no container.
- Dentro do iframe (`src/dashboard/static/office_v2/index.html` + o script de
  `zoom` responsivo, ~linha 462-509): o zoom hoje calcula a largura disponível e
  encolhe a cena. Garantir que o zoom também respeite a **altura** disponível
  (escala = min(escalaPorLargura, escalaPorAltura)) para a cena caber sem cortar.
- Conferir que `#office-v2-frame` não force largura > container (evitar overflow
  horizontal visto em viewports estreitos).

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 25.0

**Failure modes:**

- Forçar altura grande demais empurra o Trade Mode/Central de Comandos para
  muito abaixo da dobra.
- Ajuste só por CSS sem corrigir o zoom interno do iframe pode deixar a cena
  pequena demais (muita margem) ou ainda cortada.
- Mudança pode regredir o modo "solo" (página de Configurações) que usa a
  altura global do frame.

**Mitigations:**

- Usar `aspect-ratio: 560/300` no frame dentro da linha e `overflow:hidden`,
  validando em larguras 1280/1440/1920 e ≤1100px.
- Atualizar o script de zoom do office para considerar largura E altura
  disponíveis (escala = menor das duas).
- Não alterar a regra de `#office-v2-frame` fora de `.overview-office-row`
  (preservar `.office-row-solo` e demais páginas).

## Evidence

Pedido do operador (sessão 2026-05-20): "não quero ter barra de rolagem na
visualização do office na visão geral. Quero que ele apareça completo."

## Acceptance Criteria

- [ ] Na Visão Geral, o office aparece completo (sem scroll vertical/horizontal).
- [ ] Layout lado-a-lado com o Trade Mode preservado em desktop; stack ≤1100px.
- [ ] Página de Configurações (modo solo) e demais páginas inalteradas.
- [ ] Validado em 1280/1440/1920 px e em ≤1100px.
- [ ] PR aberto e vinculado a este rec_id (office-full-noscroll) para aprovação.
