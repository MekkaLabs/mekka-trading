// today_summary_failsafe.js
// =========================
// Failsafe robusto que popula sec-today-summary independente do app.js.
//
// Motivação:
//   - app.js boot pipeline (_mkRunAllBoots) pode falhar em algum boot
//     anterior a bootTodaySummary, deixando os cards com "—".
//   - Script inline foi tentado primeiro mas o CSP do dashboard
//     (script-src 'self' sem 'unsafe-inline') bloqueia inline scripts.
//   - Solução: arquivo .js servido pelo /static/ que sempre roda
//     em DOMContentLoaded + refresh 30s.
//
// Logs explícitos no console com prefixo [ts-failsafe] pra diagnóstico.
// Verifica TODOS os IDs DOM esperados e avisa caso falte algum.

(function () {
  'use strict';
  var STARTED = Date.now();

  // ---- Helpers --------------------------------------------------------

  function _fmt(n) {
    if (n === null || n === undefined) return '—';
    var f = parseFloat(n);
    if (isNaN(f)) return '—';
    return (f >= 0 ? '+' : '') + f.toFixed(2) + ' USD';
  }

  function _colorClass(n) {
    if (n === null || n === undefined || n === 0) return '';
    return n > 0 ? 'ts-green' : 'ts-red';
  }

  function _setText(id, val, className) {
    var el = document.getElementById(id);
    if (!el) {
      console.warn('[ts-failsafe] DOM ausente:', id);
      return false;
    }
    el.textContent = val;
    if (className !== undefined) {
      // Limpa classes de cor antigas e aplica a nova
      el.className = el.className
        .replace(/\bts-(green|red|muted)\b/g, '')
        .replace(/\s+/g, ' ').trim() + ' ' + className;
    }
    return true;
  }

  // ---- Render --------------------------------------------------------

  function paint(d) {
    console.log('[ts-failsafe] painting:', d);
    var openPnlNull = d.open_pnl_usd === null || d.open_pnl_usd === undefined;

    // Big cards
    var ok = 0, fail = 0;
    var trk = function (success) { if (success) ok++; else fail++; };

    trk(_setText('ts-realized-val', _fmt(d.daily_pnl_usd),
                 'ts-big-val ' + _colorClass(d.daily_pnl_usd)));
    trk(_setText('ts-realized-sub',
                 (d.trades_count_today || 0) + ' trade(s) fechado(s) hoje'));

    if (openPnlNull) {
      trk(_setText('ts-open-val', '—', 'ts-big-val ts-muted'));
    } else {
      trk(_setText('ts-open-val', _fmt(d.open_pnl_usd),
                   'ts-big-val ' + _colorClass(d.open_pnl_usd)));
    }
    trk(_setText('ts-open-sub',
                 (d.open_count || 0) + ' posição(ões) ativa(s)' +
                 (openPnlNull ? ' · sem cotação' : '')));

    var netVal = openPnlNull ? d.daily_pnl_usd : d.net_pnl_usd;
    trk(_setText('ts-net-val', _fmt(netVal),
                 'ts-big-val ' + _colorClass(netVal)));
    trk(_setText('ts-net-sub',
                 (d.day_emoji || '') +
                 (openPnlNull ? ' apenas realizado' : ' realizado + aberto')));

    console.log('[ts-failsafe] cards: ' + ok + ' OK / ' + fail + ' faltando');

    // Trades list
    var todayTrades = d.today_trades || [];
    var recentTrades = d.recent_trades || [];
    var showRecent = todayTrades.length === 0 && recentTrades.length > 0;
    var trades = (showRecent ? recentTrades : todayTrades).slice(0, 20);

    var tlist = document.getElementById('ts-trades-list');
    var tempty = document.getElementById('ts-trades-empty');
    var theader = document.getElementById('ts-trades-header');

    if (theader) {
      theader.textContent = showRecent
        ? '📅 Últimos trades (sem trades hoje)'
        : '📅 Trades de Hoje';
    }
    if (tempty) {
      tempty.style.display = trades.length ? 'none' : '';
    }
    if (tlist) {
      tlist.innerHTML = '';
      trades.forEach(function (t) {
        var pnlKnown = t.pnl_usd !== null && t.pnl_usd !== undefined;
        var pnlText = pnlKnown ? _fmt(t.pnl_usd) : '—';
        var pnlCls = pnlKnown
          ? (t.pnl_usd > 0 ? 'ts-green' : (t.pnl_usd < 0 ? 'ts-red' : ''))
          : 'ts-muted';
        var time = '';
        if (showRecent && t.date) {
          time = t.date.slice(5) + ' ' +
                 (t.timestamp ? t.timestamp.slice(11, 16) : '');
        } else {
          time = t.timestamp ? t.timestamp.slice(11, 16) : '—';
        }
        var notional = t.notional_usd
          ? '$' + parseFloat(t.notional_usd).toLocaleString('pt-BR', {
              minimumFractionDigits: 2, maximumFractionDigits: 2,
            })
          : '—';
        var row = document.createElement('div');
        row.className = 'ts-trade-row';
        row.style.cssText = 'display:grid;grid-template-columns:60px 80px 60px 80px 100px 100px;gap:8px;padding:6px 10px;border-bottom:1px dotted rgba(255,255,255,0.06);font-size:0.85em;align-items:center';
        row.innerHTML =
          '<span style="color:#888">' + time + '</span>' +
          '<span><b>' + (t.emoji || '📋') + ' ' + (t.symbol || '?') + '</b></span>' +
          '<span style="color:' + (t.side === 'long' || t.side === 'LONG' ? '#7fd17f' : '#d27575') + '">' +
          (t.side || '?').toUpperCase() + '</span>' +
          '<span style="color:#aaa">' + (t.status || '?') + '</span>' +
          '<span style="text-align:right">' + notional + '</span>' +
          '<span class="' + pnlCls + '" style="text-align:right;font-weight:bold">' +
          pnlText + '</span>';
        tlist.appendChild(row);
      });
      console.log('[ts-failsafe] trades rendered: ' + trades.length);
    } else {
      console.warn('[ts-failsafe] DOM ausente: ts-trades-list');
    }

    // Footer
    var upd = document.getElementById('ts-last-update');
    if (upd) {
      upd.textContent = new Date().toLocaleTimeString('pt-BR') +
                        ' (failsafe ' + (Date.now() - STARTED) + 'ms)';
    }
  }

  // ---- Fetch loop ----------------------------------------------------

  function load() {
    console.log('[ts-failsafe] fetching /api/today-summary…');
    fetch('/api/today-summary', { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        if (!d.ok) {
          console.error('[ts-failsafe] API ok=false:', d);
          return;
        }
        paint(d);
      })
      .catch(function (err) {
        console.error('[ts-failsafe] fetch failed:', err);
        var upd = document.getElementById('ts-last-update');
        if (upd) upd.textContent = '⚠️ Erro: ' + err.message;
      });
  }

  function start() {
    console.log('[ts-failsafe] booting (DOMContentLoaded fired)');
    // Confirma que a section existe
    var sec = document.getElementById('sec-today-summary');
    if (!sec) {
      console.error('[ts-failsafe] sec-today-summary NÃO existe no DOM!');
      return;
    }
    console.log('[ts-failsafe] sec-today-summary found, visible=' +
                (window.getComputedStyle(sec).display !== 'none'));
    load();
    setInterval(function () {
      if (!document.hidden) load();
    }, 30000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
