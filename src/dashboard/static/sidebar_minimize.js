// sidebar_minimize.js
// =====================
// Sidebar minimize toggle (2026-05-29).
//
// Comportamento:
// - Adiciona setinha no topo do <aside class="sidebar"> (já está no HTML
//   via id="sidebar-toggle" — este JS só lida com o estado).
// - Click no botão → toggle class `.sidebar--collapsed`
// - Persistência: localStorage("mekka_sidebar_collapsed") = "1" | "0"
// - Restaura estado ao carregar
// - Injeta data-emoji em cada page-nav-btn pra mostrar emoji quando colapsado
// - Adiciona keyboard shortcut: Ctrl+B (mesmo do VSCode/Notion)
// - Body ganha class "sidebar-collapsed" para main-content ajustar margin
//
// CSP-friendly: arquivo externo, sem inline scripts.

(function () {
  'use strict';

  const STORAGE_KEY = 'mekka_sidebar_collapsed';

  function getSidebar() {
    return document.querySelector('aside.sidebar');
  }

  function getToggleBtn() {
    return document.getElementById('sidebar-toggle');
  }

  function isCollapsed() {
    try {
      return localStorage.getItem(STORAGE_KEY) === '1';
    } catch (_) {
      return false;
    }
  }

  function setCollapsed(collapsed) {
    const sb = getSidebar();
    if (!sb) return;
    if (collapsed) {
      sb.classList.add('sidebar--collapsed');
      document.body.classList.add('sidebar-collapsed');
    } else {
      sb.classList.remove('sidebar--collapsed');
      document.body.classList.remove('sidebar-collapsed');
    }
    try { localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0'); } catch (_) {}
    console.log('[sidebar] ' + (collapsed ? 'collapsed' : 'expanded'));
  }

  // Extrai emoji do início do texto do botão (ex: "🏠 Overview" → "🏠")
  function extractEmoji(text) {
    if (!text) return '';
    // Match emoji ou primeiro char não-letra
    const match = text.match(/^([\p{Emoji}\p{So}\p{Cn}]+)/u);
    if (match) return match[1];
    // fallback: primeiro caractere
    return text.trim().charAt(0);
  }

  function injectEmojiAttrs() {
    const buttons = document.querySelectorAll('.page-nav-btn');
    buttons.forEach(btn => {
      if (btn.hasAttribute('data-emoji')) return;
      const emoji = extractEmoji(btn.textContent);
      if (emoji) btn.setAttribute('data-emoji', emoji);
    });
  }

  function wireToggle() {
    const btn = getToggleBtn();
    if (!btn) {
      console.warn('[sidebar] toggle button #sidebar-toggle not found');
      return;
    }
    btn.addEventListener('click', () => {
      setCollapsed(!isCollapsed());
    });
  }

  function wireKeyboardShortcut() {
    document.addEventListener('keydown', (e) => {
      // Ctrl+B (Cmd+B no Mac) — toggle sidebar
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        // Não interfere em inputs/textareas (digitar bold)
        const tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;
        e.preventDefault();
        setCollapsed(!isCollapsed());
      }
    });
  }

  function start() {
    console.log('[sidebar] booting minimize toggle');
    injectEmojiAttrs();
    wireToggle();
    wireKeyboardShortcut();
    // Restaurar estado salvo
    if (isCollapsed()) {
      // Aplica sem animação no primeiro load (evita flash)
      const sb = getSidebar();
      if (sb) {
        sb.style.transition = 'none';
        setCollapsed(true);
        // Reabilita transition após 1 frame
        requestAnimationFrame(() => {
          if (sb) sb.style.transition = '';
        });
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
