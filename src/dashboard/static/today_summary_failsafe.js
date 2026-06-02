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

  // ---- Financial topbar failsafe -------------------------------------
  //
  // A topbar (financial-topbar) é uma faixa de 7 cards no topo. Quando
  // _mkBootDashboardV2 ou um boot anterior lança exception, _mkBootTopBar
  // não roda e a topbar fica com — em tudo. Este failsafe popula
  // independente, usando os mesmos 3 endpoints (/api/pnl/summary,
  // /api/positions, /api/overview) que o app.js usa.

  function _setFtb(id, val, cls) {
    var el = document.getElementById(id);
    if (!el) {
      console.warn('[ts-failsafe] ftb DOM ausente:', id);
      return false;
    }
    el.textContent = val;
    el.className = cls ? 'ftb-value ' + cls : 'ftb-value';
    return true;
  }

  function _fmtMoney(v) {
    if (v === null || v === undefined) return '—';
    var n = parseFloat(v);
    if (isNaN(n)) return '—';
    return '$' + n.toLocaleString('pt-BR', {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
  }

  function loadTopbar() {
    console.log('[ts-failsafe] loading financial-topbar…');
    // PnL summary (equity + day PnL)
    fetch('/api/pnl/summary?window=1', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.window) return;
        var eq = d.window.latest_equity_usd;
        var pnl = d.window.pnl_usd;
        var startEq = (eq != null && pnl != null) ? eq - pnl : null;
        var pnlPct = (startEq && startEq > 0) ? (pnl / startEq * 100) : null;
        var pnlCls = pnl > 0 ? 'positive' : pnl < 0 ? 'negative' : '';
        _setFtb('ftb-wallet-val', _fmtMoney(eq));
        _setFtb('ftb-daypnl-val',
                pnl != null ? (pnl >= 0 ? '+' : '') + _fmtMoney(pnl) : '—',
                pnlCls);
        _setFtb('ftb-daypnl-pct-val',
                pnlPct != null ? (pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%' : '—',
                pnlCls);
        console.log('[ts-failsafe] topbar wallet/pnl ok');
      })
      .catch(function (err) {
        console.warn('[ts-failsafe] /api/pnl/summary failed:', err);
      });

    // Positions count
    fetch('/api/positions', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d) return;
        var count = d.count != null ? d.count : (Array.isArray(d.items) ? d.items.length : '—');
        _setFtb('ftb-positions-val', String(count));
      })
      .catch(function (err) {
        console.warn('[ts-failsafe] /api/positions failed:', err);
      });

    // Overview (risk + agents + mode)
    fetch('/api/overview', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d) return;
        // Risk
        var dd = d.drawdown_pct != null
          ? (d.drawdown_pct * 100).toFixed(1) + '%'
          : '—';
        var riskLabel = d.kill_switch_active ? '🔴 KS' : dd;
        var riskCls = d.kill_switch_active ? 'negative' : '';
        _setFtb('ftb-risk-val', riskLabel, riskCls);
        // Mode
        var mode = d.trading_mode || d.mode || '—';
        _setFtb('ftb-mode-val', String(mode).toUpperCase());
        // Agents
        var breakers = d.breakers || {};
        var total = Object.keys(breakers).length;
        var active = Object.values(breakers).filter(function (v) { return v; }).length;
        var agentLabel = active > 0
          ? '⚠️ ' + active + '/' + total
          : '🟢 ' + (total > 0 ? 'OK' : 'standby');
        _setFtb('ftb-agents-val', agentLabel);
        console.log('[ts-failsafe] topbar overview ok (mode=' + mode + ')');
      })
      .catch(function (err) {
        console.warn('[ts-failsafe] /api/overview failed:', err);
      });

    // Update timestamp
    var upEl = document.getElementById('ftb-update-val');
    if (upEl) {
      upEl.textContent = new Date().toLocaleTimeString('pt-BR', {
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      });
    }
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
    loadTopbar();
    setInterval(function () {
      if (!document.hidden) {
        load();
        loadTopbar();
      }
    }, 30000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
