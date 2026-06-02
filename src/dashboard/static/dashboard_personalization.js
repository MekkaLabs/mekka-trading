// dashboard_personalization.js
// ===============================
// Personalização avançada do dashboard (2026-05-29).
//
// 1. FAB (Floating Action Button) sempre visível pra abrir o widget
//    customizer (ele já existe em /settings, este FAB é um atalho).
// 2. Keyboard shortcut Ctrl+, (Cmd+,) — abre Settings + scroll pra customizer.
// 3. Hint visual sutil: mostra "Pressione Cmd+, pra personalizar" no primeiro
//    boot (mostra 1x, marca seen em localStorage).
//
// CSP-friendly: arquivo externo, sem inline scripts.

(function () {
  'use strict';

  const HINT_SEEN_KEY = 'mekka_personalization_hint_seen';

  function createFAB() {
    let fab = document.getElementById('widget-customizer-trigger');
    if (fab) return fab;
    fab = document.createElement('button');
    fab.id = 'widget-customizer-trigger';
    fab.type = 'button';
    fab.setAttribute('aria-label', 'Personalizar dashboard');
    fab.title = 'Personalizar painéis (Cmd+,)';
    fab.innerHTML = '🎨';
    fab.addEventListener('click', openCustomizer);
    document.body.appendChild(fab);
    return fab;
  }

  function openCustomizer() {
    // 1. Navega pra page settings
    try {
      // _mkSetPage é função do app.js
      if (typeof window._mkSetPage === 'function') {
        window._mkSetPage('settings');
      } else {
        // fallback: dispara click no botão settings
        const settingsBtn = document.querySelector('.page-nav-btn[data-page="settings"]');
        if (settingsBtn) settingsBtn.click();
      }
    } catch (_) {}
    // 2. Scroll suave até o customizer após renderizar
    setTimeout(() => {
      const target = document.getElementById('widget-customizer');
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        // Highlight visual breve
        target.style.transition = 'box-shadow 300ms ease';
        target.style.boxShadow = '0 0 0 3px #5be8f5';
        setTimeout(() => { target.style.boxShadow = ''; }, 1500);
      }
    }, 300);
  }

  function wireKeyboardShortcut() {
    document.addEventListener('keydown', (e) => {
      // Cmd/Ctrl + , (vírgula)
      if ((e.ctrlKey || e.metaKey) && e.key === ',') {
        const tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;
        e.preventDefault();
        openCustomizer();
      }
    });
  }

  function maybeShowHint() {
    try {
      if (localStorage.getItem(HINT_SEEN_KEY)) return;
      // Mostra após 3s, persiste 8s
      setTimeout(() => {
        const hint = document.createElement('div');
        hint.style.cssText = (
          'position:fixed;bottom:80px;right:24px;z-index:9001;' +
          'background:rgba(91,232,245,0.16);border:1px solid rgba(91,232,245,0.45);' +
          'color:#5be8f5;padding:12px 18px;border-radius:8px;font-size:0.88rem;' +
          'box-shadow:0 6px 24px rgba(0,0,0,0.4);max-width:280px;' +
          'animation:slideInRight 300ms ease-out'
        );
        hint.innerHTML = (
          '<div style="font-weight:bold;margin-bottom:4px">🎨 Personalize seu dashboard</div>' +
          '<div style="color:#aac;font-size:0.82rem">Cmd+, para abrir personalizador<br>' +
          'Cmd+B para minimizar a sidebar<br>' +
          'Use o botão 🎨 no canto inferior</div>'
        );
        document.body.appendChild(hint);
        setTimeout(() => {
          hint.style.transition = 'opacity 300ms';
          hint.style.opacity = '0';
          setTimeout(() => hint.remove(), 350);
        }, 8000);
        localStorage.setItem(HINT_SEEN_KEY, '1');
      }, 3000);
    } catch (_) {}
  }

  function start() {
    console.log('[personalization] booting');
    createFAB();
    wireKeyboardShortcut();
    maybeShowHint();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
