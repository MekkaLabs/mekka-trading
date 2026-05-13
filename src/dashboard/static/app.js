const statusPill = document.getElementById('status-pill');
const langToggle = document.getElementById('lang-toggle');
const themeToggleBtn = document.getElementById('theme-toggle');
const prefsResetBtn = document.getElementById('prefs-reset');
const metricsRoot = document.getElementById('metrics');
const signalsBody = document.getElementById('signals-body');
const tradesBody = document.getElementById('trades-body');
const auditLog = document.getElementById('audit-log');
const layerMap = document.getElementById('layer-map');
const timelineRoot = document.getElementById('timeline');
const riskHeatmap = document.getElementById('risk-heatmap');
const anomalyConsole = document.getElementById('anomaly-console');
const symbolTimeline = document.getElementById('symbol-timeline');
const globalAlerts = document.getElementById('global-alerts');
const heroSla = document.getElementById('hero-sla');
const filterSymbol = document.getElementById('filter-symbol');
const filterHero = document.getElementById('filter-hero');
const filterEvent = document.getElementById('filter-event');
const replayLiveBtn = document.getElementById('replay-live');
const replayPrevBtn = document.getElementById('replay-prev');
const replayPlayBtn = document.getElementById('replay-play');
const replayNextBtn = document.getElementById('replay-next');
const replaySnapshotSelect = document.getElementById('replay-snapshot');
const replayExportJsonBtn = document.getElementById('replay-export-json');
const replayExportCsvBtn = document.getElementById('replay-export-csv');
const exportStartUtc = document.getElementById('export-start-utc');
const exportEndUtc = document.getElementById('export-end-utc');
const replayStatus = document.getElementById('replay-status');
const incidentLatestBtn = document.getElementById('incident-latest');
const incidentBundleSelect = document.getElementById('incident-bundle-select');
const compareA = document.getElementById('compare-a');
const compareB = document.getElementById('compare-b');
const compareRunBtn = document.getElementById('compare-run');
const compareOutput = document.getElementById('compare-output');
const incidentDownloadBtn = document.getElementById('incident-download');
const incidentDownloadSelectedBtn = document.getElementById('incident-download-selected');
const chartsRefreshBtn = document.getElementById('charts-refresh');
const queueRefreshBtn = document.getElementById('queue-refresh');
const queueSeverityFilter = document.getElementById('queue-severity-filter');
const queueSearch = document.getElementById('queue-search');
const queuePrevBtn = document.getElementById('queue-prev');
const queueNextBtn = document.getElementById('queue-next');
const queuePageStatus = document.getElementById('queue-page-status');
const incidentExportCsvBtn = document.getElementById('incident-export-csv');
const marketSymbol = document.getElementById('market-symbol');
const marketTimeframe = document.getElementById('market-timeframe');
const marketRefreshInterval = document.getElementById('market-refresh-interval');
const marketRefreshBtn = document.getElementById('market-refresh');
const marketLiveToggleBtn = document.getElementById('market-live-toggle');
const marketStatus = document.getElementById('market-status');
const marketBreakerPill = document.getElementById('market-breaker-pill');
const marketStats = document.getElementById('market-stats');
const marketChartEl = document.getElementById('market-chart');
const orderbookStatus = document.getElementById('orderbook-status');
const orderbookSummary = document.getElementById('orderbook-summary');
const orderbookBids = document.getElementById('orderbook-bids');
const orderbookAsks = document.getElementById('orderbook-asks');
const tapeStatus = document.getElementById('tape-status');
const tradeTape = document.getElementById('trade-tape');
const marketDiagStatus = document.getElementById('market-diag-status');
const marketDiag = document.getElementById('market-diag');
const chartsStatus = document.getElementById('charts-status');
const incidentQueueRoot = document.getElementById('incident-queue');
const incidentQueueDetail = document.getElementById('incident-queue-detail');
const chartCanvases = {
  signals: document.getElementById('chart-signals'),
  trades: document.getElementById('chart-trades'),
  alerts: document.getElementById('chart-alerts'),
  equity: document.getElementById('chart-equity'),
  daily_pnl: document.getElementById('chart-daily-pnl'),
  drawdown: document.getElementById('chart-drawdown'),
  benchmark: document.getElementById('chart-benchmark'),
  trades_timeline: document.getElementById('chart-trades-timeline'),
};
const tradesTimelineHours = document.getElementById('trades-timeline-hours');
const tradesTimelineRefresh = document.getElementById('trades-timeline-refresh');
const tradesTimelineStatus = document.getElementById('trades-timeline-status');
const pnlWindowSelect = document.getElementById('pnl-window');
const pnlRefreshBtn = document.getElementById('pnl-refresh');
const pnlStatus = document.getElementById('pnl-status');
const pnlCards = document.getElementById('pnl-cards');
const killswitchStatus = document.getElementById('killswitch-status');
const killswitchEngageBtn = document.getElementById('killswitch-engage');
const killswitchReleaseBtn = document.getElementById('killswitch-release');
const authButton = document.getElementById('auth-button');
const authState = document.getElementById('auth-state');
const authModal = document.getElementById('auth-modal');
const authModalClose = document.getElementById('auth-modal-close');
const authPassword = document.getElementById('auth-password');
const authError = document.getElementById('auth-error');
const authSubmitBtn = document.getElementById('auth-submit');
const authCancelBtn = document.getElementById('auth-cancel');
const killswitchModal = document.getElementById('killswitch-modal');
const killswitchModalTitle = document.getElementById('killswitch-modal-title');
const killswitchModalText = document.getElementById('killswitch-modal-text');
const killswitchModalReason = document.getElementById('killswitch-modal-reason');
const killswitchModalConfirm = document.getElementById('killswitch-modal-confirm');
const killswitchModalConfirmLabel = document.getElementById('killswitch-modal-confirm-label');
const killswitchModalError = document.getElementById('killswitch-modal-error');
const killswitchModalSubmit = document.getElementById('killswitch-modal-submit');
const killswitchModalCancel = document.getElementById('killswitch-modal-cancel');
const killswitchModalClose = document.getElementById('killswitch-modal-close');
const filterMode = document.getElementById('filter-mode');
const positionsRefreshBtn = document.getElementById('positions-refresh');
const positionsStatus = document.getElementById('positions-status');
const positionsBody = document.getElementById('positions-body');
const internalsRefreshBtn = document.getElementById('internals-refresh');
const internalsStatus = document.getElementById('internals-status');
const internalsCards = document.getElementById('internals-cards');
const internalsRawPre = document.getElementById('internals-raw');
const riskModal = document.getElementById('risk-modal');
const riskModalBody = document.getElementById('risk-modal-body');
const riskModalTitle = document.getElementById('risk-modal-title');
const riskModalClose = document.getElementById('risk-modal-close');
const sidebarAnchors = Array.from(document.querySelectorAll('.sidebar-nav a[href^="#"]'));

const officeV2Root = document.getElementById('office-v2-root');

let currentOverview = null;
let tick = 0;
let lastPayload = null;
let sceneAlertLevel = 'normal';
let currentRiskDrilldown = {};
let hasGlobalCriticalAlert = false;
let replayMode = 'live';
let replaySnapshots = [];
let replayIndex = -1;
let replayTimer = null;
let queueSearchDebounce = null;
const chartInstances = {
  signals: null, trades: null, alerts: null,
  equity: null, daily_pnl: null, drawdown: null,
};
let chartsAutoRefreshTimer = null;
let queueAutoRefreshTimer = null;
let pnlAutoRefreshTimer = null;
let killswitchAutoRefreshTimer = null;
let killswitchAction = null; // 'engage' | 'release'
let positionsAutoRefreshTimer = null;
let internalsAutoRefreshTimer = null;
let queueOffset = 0;
const queuePageSize = 15;
let marketAutoRefreshTimer = null;
let marketLivePaused = false;
let marketRefreshMs = 3000;
let marketChart = null;
let marketSeries = null;
let marketVolumeSeries = null;
let marketFirstRender = true;
let marketPriceLine = null;
let marketTickerWs = null;
let marketTickerReconnectTimer = null;
let marketTickerRetryAttempt = 0;
let lastMarketSnapshot = null;
let marketFallbackMode = false;
let tradingViewWidget = null;
let tradingViewReady = false;
let tradingViewRetryTimer = null;
let tradingViewScriptRequested = false;
const TRADINGVIEW_SCRIPT_URLS = ['https://s3.tradingview.com/tv.js', 'https://s3.tradingview.com/tv.js'];
const PREF_KEY = 'mekka_dashboard_prefs_v1';
let currentLang = 'pt';
let officeV2Mounted = false;

const I18N = window.MekkaI18n?.dict || { pt: {}, en: {} };

const HELP_TIPS = {
  'Market Live (Exchange View)': 'Candles em tempo real com volume e métricas 24h para leitura tática como em plataformas de corretora.',
  'Replay Player': 'Controle histórico operacional: navegue snapshots, exporte janelas e compare cenários para investigação.',
  'Replay Charts (Series Temporais)': 'Séries de sinais, trades, alertas e severidade ao longo do tempo para detectar mudanças de regime.',
  'Incident Investigation Queue': 'Fila priorizada por score de severidade para orientar qual incidente investigar primeiro.',
  'Mission Metrics': 'Resumo macro da missão atual: sinais, trades e execuções mais recentes.',
  'Pixel 3D Office': 'Representação visual do estado operacional. Mudanças de alerta alteram a ambientação.',
  'Layer Command Map (L1-L4)': 'Saúde por camada (análise, estratégia, risco/execução, comando), com status dos heróis.',
  'Agents Pixel Roster 3D': 'Roster visual dos agentes com pixel art e paletas clássicas para identificação rápida.',
  'Filters': 'Filtra eventos, símbolos e heróis em tabelas e painéis de investigação.',
  'Nick Fury Timeline': 'Linha temporal de eventos de comando/orquestração do Nick Fury.',
  'Timeline Por Símbolo': 'Sequência de execução por ativo no pipeline ProfessorX → Vision → Batman → IronMan.',
  'Hero SLA (s)': 'Métricas de latência por etapa/herói (AVG e P95) para avaliar degradacão operacional.',
  'Batman Risk Heatmap': 'Mapa de aprovações/reduções/rejeições/kill switch por símbolo com drilldown detalhado.',
  'Spider-Man Anomaly Console': 'Consolida anomalias detectadas e indicações de pause de operação.',
  'Vision Signals': 'Sinais estratégicos gerados pelo Vision (ação e confiança).',
  'Iron Man Executions': 'Execuções enviadas pelo Iron Man com status e notional.',
  'Hero Audit Stream': 'Trilha de auditoria bruta dos eventos dos agentes para forense.',
  'Mini Manual Operacional': 'Guia rápido de leitura para reduzir tempo de onboarding e resposta a incidentes.',
};

const SPRITE_PATTERN = [
  '...1111...',
  '..122221..',
  '..122221..',
  '..133331..',
  '..144441..',
  '..144441..',
  '..144441..',
  '..155551..',
  '..155551..',
  '..166661..',
  '..166661..',
  '.11....11.',
];

const AGENT_PALETTES = [
  ['Superman', { 1: '#1c2a66', 2: '#f6d0a8', 3: '#2d53c8', 4: '#d7322f', 5: '#2d53c8', 6: '#d7322f' }],
  ['Doctor Strange', { 1: '#29143f', 2: '#f4d0b0', 3: '#7f2ca8', 4: '#b0122f', 5: '#2f4fb8', 6: '#452060' }],
  ['Black Panther', { 1: '#0b0f18', 2: '#6a6f80', 3: '#1d2433', 4: '#40296b', 5: '#1d2433', 6: '#0b0f18' }],
  ['Thor', { 1: '#4a4f60', 2: '#f4d8b8', 3: '#3553c2', 4: '#be2b2b', 5: '#1f2d59', 6: '#4a4f60' }],
  ['Aquaman', { 1: '#145b48', 2: '#f2cda8', 3: '#2b8d67', 4: '#d0862b', 5: '#2b8d67', 6: '#d0862b' }],
  ['Spider-Man', { 1: '#5b0f16', 2: '#f4d0b0', 3: '#c71f2d', 4: '#1a2f7a', 5: '#c71f2d', 6: '#1a2f7a' }],
  ['Vision', { 1: '#264b28', 2: '#9ac57f', 3: '#3f8f45', 4: '#e2b542', 5: '#b3232b', 6: '#2d8b49' }],
  ['Professor X', { 1: '#2c3757', 2: '#f0ceb0', 3: '#4a5b84', 4: '#6b2a2a', 5: '#3a4a70', 6: '#1f2740' }],
  ['Batman', { 1: '#111826', 2: '#f2cfad', 3: '#1d2a45', 4: '#7d6b2d', 5: '#1d2a45', 6: '#111826' }],
  ['Iron Man', { 1: '#5f1717', 2: '#f1caa5', 3: '#be2b2b', 4: '#d3a132', 5: '#be2b2b', 6: '#d3a132' }],
  ['Nick Fury', { 1: '#1a1d24', 2: '#9d7a5f', 3: '#3a3f4f', 4: '#2c2f3a', 5: '#2c2f3a', 6: '#1a1d24' }],
  ['Wolverine', { 1: '#1f2d7d', 2: '#f1c9a7', 3: '#2852d6', 4: '#d7b228', 5: '#2852d6', 6: '#d7b228' }],
  ['Flash', { 1: '#5f1717', 2: '#f0caaa', 3: '#c92626', 4: '#d8b032', 5: '#c92626', 6: '#d8b032' }],
  ['Deadpool', { 1: '#210f12', 2: '#f3cfb1', 3: '#d0262a', 4: '#2a2f3a', 5: '#d0262a', 6: '#2a2f3a' }],
];

// XSS hardening — every value reaching innerHTML must pass through this.
// Symbols, agent names, audit messages, alert strings, exchange responses
// and even snapshot filenames flow from external sources (LLMs, news APIs,
// exchanges, databases) and could contain `<script>` payloads. Escaping at
// render time blocks the entire class without us having to whitelist sources.
const _ESCAPE_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value).replace(/[&<>"']/g, (ch) => _ESCAPE_MAP[ch]);
}

function fmtTime(ts) {
  if (ts === null || ts === undefined || ts === '') return '-';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '-';
  return d.toLocaleTimeString('pt-BR', { hour12: false });
}

function fmtMoney(v) {
  return Number(v || 0).toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

function fmtCompact(v) {
  return Number(v || 0).toLocaleString('en-US', { notation: 'compact', maximumFractionDigits: 2 });
}

function fmtPercent(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return '-';
  return `${(n * 100).toFixed(0)}%`;
}

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(PREF_KEY) || '{}');
  } catch {
    return {};
  }
}

function savePrefs(partial) {
  try {
    const current = loadPrefs();
    localStorage.setItem(PREF_KEY, JSON.stringify({ ...current, ...partial }));
  } catch {
    // noop
  }
}

function resetPrefs() {
  try {
    localStorage.removeItem(PREF_KEY);
  } catch {
    // noop
  }
  window.location.reload();
}

function t(key) {
  return I18N[currentLang]?.[key] || I18N.pt[key] || key;
}

function applyLanguage(lang) {
  currentLang = (lang === 'en') ? 'en' : 'pt';
  document.documentElement.lang = currentLang === 'pt' ? 'pt-BR' : 'en';
  if (langToggle) langToggle.value = currentLang;

  const setText = (selector, text) => {
    const el = document.querySelector(selector);
    if (el) el.textContent = text;
  };
  setText('#sec-live-market h2', t('market_live'));
  setText('#market-refresh', t('market_refresh'));
  setText('label[for="lang-toggle"]', t('language_label'));
  setText('#nav-label-overview', t('nav_overview'));
  setText('#nav-label-command', t('nav_command'));
  setText('#nav-label-replay-risk', t('nav_replay_risk'));
  setText('#nav-label-ops', t('nav_ops'));
  setText('#nav-label-execution', t('nav_execution'));
  setText('#nav-link-market-live', t('nav_market_live'));
  setText('#nav-link-mission-metrics', t('nav_mission_metrics'));
  setText('#nav-link-office', t('nav_office'));
  setText('#nav-link-layers', t('nav_layers'));
  setText('#nav-link-agents', t('nav_agents'));
  setText('#nav-link-manual', t('nav_manual'));
  setText('#nav-link-replay-player', t('nav_replay_player'));
  setText('#nav-link-replay-charts', t('nav_replay_charts'));
  setText('#nav-link-incident-queue', t('nav_incident_queue'));
  setText('#nav-link-killswitch', t('nav_killswitch'));
  setText('#nav-link-pnl', t('nav_pnl'));
  setText('#nav-link-positions', t('nav_positions'));
  setText('#nav-link-risk', t('nav_risk'));
  setText('#nav-link-anomalies', t('nav_anomalies'));
  setText('#nav-link-internals', t('nav_internals'));
  setText('#nav-link-signals', t('nav_signals'));
  setText('#nav-link-trades', t('nav_trades'));
  setText('#nav-link-audit', t('nav_audit'));
  setText('label[for="market-symbol"]', t('market_pair'));
  setText('label[for="market-timeframe"]', t('market_tf'));
  setText('label[for="market-refresh-interval"]', t('market_refresh_label'));
  setText('#replay-prev', t('prev'));
  setText('#replay-next', t('next'));
  setText('#queue-prev', t('prev'));
  setText('#queue-next', t('next'));
  setText('#incident-latest', t('incident_latest'));
  setText('#incident-download', t('download_bundle'));
  setText('#charts-refresh', t('refresh_charts'));
  setText('#queue-refresh', t('refresh_queue'));
  setText('#sec-replay-player h2', t('replay_player'));
  setText('#sec-replay-charts h2', t('replay_charts'));
  setText('#sec-incident-queue h2', t('incident_queue'));
  setText('#sec-manual h2', t('mini_manual'));
  setText('#sec-signals h2', t('vision_signals'));
  setText('#sec-trades h2', t('executions'));
  setText('#sec-audit h2', t('audit'));
  setText('#sec-risk h2', t('risk_heatmap'));
  setText('#sec-anomalies h2', t('anomaly_console'));
  setText('#sec-positions h2', t('open_positions'));
  setText('#sec-internals h2', t('internals'));
  setText('#sec-filters h2', t('filters'));
  setText('#sec-timeline h2', t('timeline'));
  setText('#sec-symbol-timeline h2', t('symbol_timeline'));
  setText('#sec-hero-sla h2', t('hero_sla'));
  setText('.orderbook-wrap .orderbook-head strong', t('orderbook_depth'));
  setText('.tape-wrap .orderbook-head strong', t('tape'));
  const diagHeads = document.querySelectorAll('.tape-wrap .orderbook-head strong');
  if (diagHeads[1]) diagHeads[1].textContent = t('diagnostics');
  if (prefsResetBtn) prefsResetBtn.textContent = t('reset_prefs');
  if (marketLiveToggleBtn) {
    marketLiveToggleBtn.textContent = marketLivePaused ? t('market_resume') : t('market_pause');
  }
  if (themeToggleBtn) {
    const isLight = document.body.getAttribute('data-theme') === 'light';
    themeToggleBtn.textContent = isLight ? t('theme_dark') : t('theme_light');
  }
  remountOfficeV2Panel();
}

function applyTheme(theme) {
  const t = theme === 'light' ? 'light' : 'dark';
  document.body.setAttribute('data-theme', t);
  if (themeToggleBtn) themeToggleBtn.textContent = t === 'light' ? (currentLang === 'pt' ? 'Modo Escuro' : 'Dark Mode') : (currentLang === 'pt' ? 'Modo Claro' : 'Light Mode');
  remountOfficeV2Panel();
}

function mountOfficeV2Panel() {
  if (!officeV2Root || typeof window.mountOfficeV2 !== 'function') return;
  const theme = document.body.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  const language = currentLang === 'en' ? 'en' : 'pt';
  const provider = typeof window.createOfficeDataProvider === 'function'
    ? window.createOfficeDataProvider()
    : undefined;
  try {
    window.mountOfficeV2({
      root: officeV2Root,
      theme,
      language,
      dataProvider: provider,
    });
    officeV2Mounted = true;
  } catch (err) {
    officeV2Mounted = false;
    if (officeV2Root) {
      officeV2Root.innerHTML = `<div class="muted-line">Office V2 indisponível: ${escapeHtml(err?.message || 'erro desconhecido')}</div>`;
    }
  }
}

function remountOfficeV2Panel() {
  if (!officeV2Root || typeof window.mountOfficeV2 !== 'function') return;
  if (!officeV2Mounted) {
    mountOfficeV2Panel();
    return;
  }
  mountOfficeV2Panel();
}

function applyPrefs() {
  const p = loadPrefs();
  if (marketSymbol && p.marketSymbol) marketSymbol.value = p.marketSymbol;
  if (marketTimeframe && p.marketTimeframe) marketTimeframe.value = p.marketTimeframe;
  if (marketRefreshInterval && p.marketRefreshMs) {
    marketRefreshInterval.value = String(p.marketRefreshMs);
    const parsed = Number(p.marketRefreshMs);
    if (Number.isFinite(parsed) && parsed >= 1000) marketRefreshMs = parsed;
  }
  if (queueSeverityFilter && p.queueSeverity) queueSeverityFilter.value = p.queueSeverity;
  if (queueSearch && p.queueSearch) queueSearch.value = p.queueSearch;
  if (filterSymbol && p.filterSymbol) filterSymbol.value = p.filterSymbol;
  if (filterHero && p.filterHero) filterHero.value = p.filterHero;
  if (filterEvent && p.filterEvent) filterEvent.value = p.filterEvent;
  if (pnlWindowSelect && p.pnlWindow) pnlWindowSelect.value = p.pnlWindow;
  if (filterMode && p.filterMode) filterMode.value = p.filterMode;
  if (p.lang) currentLang = p.lang === 'en' ? 'en' : 'pt';
  applyTheme(p.theme || 'dark');
  applyLanguage(currentLang);
  if (typeof p.marketLivePaused === 'boolean') {
    marketLivePaused = p.marketLivePaused;
    if (marketLiveToggleBtn) {
      marketLiveToggleBtn.textContent = marketLivePaused ? t('market_resume') : t('market_pause');
    }
  }
}

function enhanceTitlesWithHelp() {
  document.querySelectorAll('.panel h2').forEach((h2) => {
    if (h2.dataset.helpApplied === '1') return;
    const text = h2.textContent.trim();
    const tip = HELP_TIPS[text];
    if (!tip) return;
    const row = document.createElement('div');
    row.className = 'title-row';
    const dot = document.createElement('span');
    dot.className = 'help-dot';
    dot.textContent = '?';
    dot.setAttribute('data-tip', tip);
    h2.replaceWith(row);
    row.appendChild(h2);
    row.appendChild(dot);
    h2.dataset.helpApplied = '1';
  });
}

function renderAgentsRoster() {
  const root = document.getElementById('agents-roster');
  if (!root) return;
  root.innerHTML = AGENT_PALETTES.map(([name]) => `
    <div class="agent-card">
      <div class="sprite3d" data-agent="${name}"></div>
      <div class="agent-name">${name}</div>
    </div>
  `).join('');

  root.querySelectorAll('.sprite3d').forEach((el, idx) => {
    const palette = AGENT_PALETTES[idx][1];
    let html = '';
    for (let y = 0; y < SPRITE_PATTERN.length; y += 1) {
      const row = SPRITE_PATTERN[y];
      for (let x = 0; x < row.length; x += 1) {
        const k = row[x];
        if (k === '.') continue;
        const color = palette[k] || '#999';
        html += `<span class="cell" style="left:calc(var(--px)*${x});top:calc(var(--px)*${y});--c:${color}"></span>`;
      }
    }
    el.innerHTML = html;
  });
}

function initMarketChart() {
  if (initTradingViewWidget()) return true;
  if (!marketChartEl) return false;
  if (typeof LightweightCharts === 'undefined') {
    marketFallbackMode = true;
    return false;
  }
  if (marketChart) return;
  marketChart = LightweightCharts.createChart(marketChartEl, {
    layout: { background: { color: '#0b1325' }, textColor: '#95a3c4' },
    grid: { vertLines: { color: 'rgba(72,151,255,0.08)' }, horzLines: { color: 'rgba(72,151,255,0.08)' } },
    timeScale: { borderColor: '#2b416b', timeVisible: true },
    rightPriceScale: { borderColor: '#2b416b' },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    width: marketChartEl.clientWidth || 900,
    height: 430,
  });
  marketSeries = marketChart.addCandlestickSeries({
    upColor: '#2bc4b5',
    downColor: '#ff5c66',
    borderVisible: false,
    wickUpColor: '#2bc4b5',
    wickDownColor: '#ff5c66',
  });
  marketVolumeSeries = marketChart.addHistogramSeries({
    color: '#2bc4b599',
    priceFormat: { type: 'volume' },
    priceScaleId: 'left',
  });
  marketChart.priceScale('left').applyOptions({
    scaleMargins: { top: 0.78, bottom: 0 },
    borderColor: '#2b416b',
  });
  marketChart.priceScale('right').applyOptions({
    scaleMargins: { top: 0.08, bottom: 0.28 },
    borderColor: '#2b416b',
  });
  window.addEventListener('resize', () => {
    if (!marketChart || !marketChartEl) return;
    marketChart.applyOptions({ width: marketChartEl.clientWidth || 900 });
  });
  return true;
}

function toTradingViewSymbol(symbol) {
  return `BINANCE:${String(symbol || 'BTCUSDT').toUpperCase()}`;
}

function toTradingViewInterval(tf) {
  const map = { '1m': '1', '5m': '5', '15m': '15', '1h': '60', '4h': '240', '1d': '1D' };
  return map[tf] || '60';
}

function ensureTradingViewScript() {
  if (typeof TradingView !== 'undefined' && typeof TradingView.widget === 'function') return;
  if (tradingViewScriptRequested) return;
  tradingViewScriptRequested = true;
  const script = document.createElement('script');
  script.src = TRADINGVIEW_SCRIPT_URLS[0];
  script.async = true;
  script.onload = () => {
    tradingViewScriptRequested = false;
  };
  script.onerror = () => {
    tradingViewScriptRequested = false;
  };
  document.head.appendChild(script);
}

function initTradingViewWidget() {
  if (!marketChartEl) return false;
  if (tradingViewWidget) return true;
  if (typeof TradingView === 'undefined' || typeof TradingView.widget !== 'function') {
    ensureTradingViewScript();
    return false;
  }
  marketChartEl.innerHTML = '';
  try {
    tradingViewWidget = new TradingView.widget({
      autosize: true,
      symbol: toTradingViewSymbol(marketSymbol?.value || 'BTCUSDT'),
      interval: toTradingViewInterval(marketTimeframe?.value || '1h'),
      timezone: 'Etc/UTC',
      theme: 'dark',
      style: '1',
      locale: 'pt',
      withdateranges: true,
      hide_top_toolbar: false,
      hide_side_toolbar: false,
      allow_symbol_change: true,
      save_image: true,
      details: true,
      hotlist: true,
      calendar: true,
      studies: ['Volume@tv-basicstudies'],
      enabled_features: [
        'study_templates',
        'items_favoriting',
        'header_fullscreen_button',
        'header_compare',
        'left_toolbar',
      ],
      disabled_features: ['use_localstorage_for_settings'],
      container_id: 'market-chart',
    });
    tradingViewReady = true;
    marketFallbackMode = false;
    return true;
  } catch {
    tradingViewReady = false;
    tradingViewWidget = null;
    return false;
  }
}

function scheduleTradingViewRetry() {
  if (tradingViewReady || tradingViewRetryTimer) return;
  let attempts = 0;
  tradingViewRetryTimer = setInterval(() => {
    attempts += 1;
    if (attempts % 4 === 0) ensureTradingViewScript();
    const ok = initTradingViewWidget();
    if (ok) {
      tradingViewReady = true;
      clearInterval(tradingViewRetryTimer);
      tradingViewRetryTimer = null;
      loadMarketCandles();
      return;
    }
    if (attempts >= 30) {
      clearInterval(tradingViewRetryTimer);
      tradingViewRetryTimer = null;
    }
  }, 500);
}

function syncTradingViewSymbolAndInterval() {
  if (!tradingViewWidget || !tradingViewReady || typeof tradingViewWidget.activeChart !== 'function') return;
  try {
    const chart = tradingViewWidget.activeChart();
    if (!chart) return;
    const symbol = toTradingViewSymbol(marketSymbol?.value || 'BTCUSDT');
    const interval = toTradingViewInterval(marketTimeframe?.value || '1h');
    if (typeof chart.setSymbol === 'function') {
      chart.setSymbol(symbol, interval);
    }
    if (typeof chart.setResolution === 'function') {
      chart.setResolution(interval);
    }
  } catch {
    // noop
  }
}

function renderMarketFallback(candles) {
  if (!marketChartEl || !candles?.length) return;
  const w = Math.max(320, marketChartEl.clientWidth || 900);
  const h = 430;
  const pad = 24;
  const closes = candles.map((c) => Number(c.close || 0)).filter((x) => Number.isFinite(x));
  if (!closes.length) return;
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = Math.max(1e-9, max - min);
  const step = (w - pad * 2) / Math.max(1, closes.length - 1);
  const points = closes.map((v, i) => {
    const x = pad + i * step;
    const y = pad + (1 - ((v - min) / span)) * (h - pad * 2);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(' ');
  const last = closes[closes.length - 1];
  marketChartEl.innerHTML = `
    <svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" aria-label="Market fallback chart">
      <rect x="0" y="0" width="${w}" height="${h}" fill="#0b1325"></rect>
      <polyline fill="none" stroke="#45d0ff" stroke-width="2" points="${points}" />
      <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="rgba(149,163,196,0.35)" />
      <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${h - pad}" stroke="rgba(149,163,196,0.35)" />
      <text x="${w - pad}" y="${pad + 2}" text-anchor="end" fill="#95a3c4" font-size="12">HIGH ${max.toLocaleString('en-US')}</text>
      <text x="${w - pad}" y="${h - pad + 14}" text-anchor="end" fill="#95a3c4" font-size="12">LOW ${min.toLocaleString('en-US')}</text>
      <text x="${pad}" y="${pad + 2}" fill="#d8e8ff" font-size="12">LAST ${last.toLocaleString('en-US')}</text>
    </svg>
  `;
}

function renderMarketStats(data) {
  const s = data.stats || {};
  const pct = Number(s.price_change_pct_24h || 0);
  const cls = pct >= 0 ? 'pos' : 'neg';
  marketStats.innerHTML = `
    <div class="mstat"><span>Last Price</span><strong>${Number(s.last_price || 0).toLocaleString('en-US')}</strong></div>
    <div class="mstat"><span>24h Change</span><strong class="${cls}">${pct.toFixed(2)}%</strong></div>
    <div class="mstat"><span>24h Volume</span><strong>${fmtCompact(s.volume_24h)}</strong></div>
    <div class="mstat"><span>24h Range</span><strong>${Number(s.low_24h || 0).toLocaleString('en-US')} - ${Number(s.high_24h || 0).toLocaleString('en-US')}</strong></div>
  `;
}

function renderOrderBook(data) {
  const s = data.summary || {};
  const imbalancePct = Number(s.imbalance || 0) * 100;
  orderbookSummary.innerHTML = `
    <div class="mstat"><span>Best Bid</span><strong class="buy">${Number(s.best_bid || 0).toLocaleString('en-US')}</strong></div>
    <div class="mstat"><span>Best Ask</span><strong class="sell">${Number(s.best_ask || 0).toLocaleString('en-US')}</strong></div>
    <div class="mstat"><span>Spread</span><strong>${Number(s.spread || 0).toFixed(4)} (${Number(s.spread_bps || 0).toFixed(2)} bps)</strong></div>
    <div class="mstat"><span>Book Imbalance</span><strong class="${imbalancePct >= 0 ? 'buy' : 'sell'}">${imbalancePct.toFixed(2)}%</strong></div>
  `;

  const fmt = (n) => Number(n || 0).toLocaleString('en-US', { maximumFractionDigits: 4 });
  const bidMax = Math.max(1, ...(data.bids || []).map((x) => x.price * x.qty));
  const askMax = Math.max(1, ...(data.asks || []).map((x) => x.price * x.qty));
  orderbookBids.innerHTML = (data.bids || []).map((x) => (
    `<div class="book-row buy" style="--heat:${Math.max(4, Math.min(100, (x.price * x.qty / bidMax) * 100)).toFixed(1)}%"><span class="p buy">${fmt(x.price)}</span><span>${fmt(x.qty)}</span><span>${fmt(x.price * x.qty)}</span></div>`
  )).join('');
  orderbookAsks.innerHTML = (data.asks || []).map((x) => (
    `<div class="book-row sell" style="--heat:${Math.max(4, Math.min(100, (x.price * x.qty / askMax) * 100)).toFixed(1)}%"><span class="p sell">${fmt(x.price)}</span><span>${fmt(x.qty)}</span><span>${fmt(x.price * x.qty)}</span></div>`
  )).join('');
}

function updateBreakerPill(itemsObj) {
  if (!marketBreakerPill) return;
  const items = Object.values(itemsObj || {});
  const open = items.filter((v) => Boolean(v?.breaker_open));
  if (!items.length) {
    marketBreakerPill.className = 'breaker-pill warn';
    marketBreakerPill.textContent = 'BREAKER UNKNOWN';
    return;
  }
  if (!open.length) {
    marketBreakerPill.className = 'breaker-pill ok';
    marketBreakerPill.textContent = 'BREAKER CLOSED';
    return;
  }
  const maxUntil = Math.max(...open.map((v) => Number(v?.breaker_open_until_s || 0)));
  marketBreakerPill.className = 'breaker-pill critical';
  marketBreakerPill.textContent = `BREAKER OPEN ${Math.ceil(maxUntil)}s`;
}

async function loadMarketStatus() {
  if (!marketBreakerPill) return;
  try {
    const res = await fetch('/api/market/status');
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    if (data.state === 'healthy') {
      marketBreakerPill.className = 'breaker-pill ok';
      marketBreakerPill.textContent = 'BREAKER CLOSED';
      return;
    }
    if (data.state === 'warning') {
      marketBreakerPill.className = 'breaker-pill warn';
      marketBreakerPill.textContent = `BREAKER WARN • err ${data.errors ?? 0}`;
      return;
    }
    if (data.state === 'degraded') {
      marketBreakerPill.className = 'breaker-pill critical';
      marketBreakerPill.textContent = `BREAKER OPEN • keys ${data.breaker_open_keys ?? 0} • ${Math.ceil(Number(data.next_recovery_s || 0))}s`;
      return;
    }
    marketBreakerPill.className = 'breaker-pill warn';
    marketBreakerPill.textContent = 'BREAKER UNKNOWN';
  } catch {
    marketBreakerPill.className = 'breaker-pill warn';
    marketBreakerPill.textContent = 'BREAKER UNKNOWN';
  }
}

async function loadMarketCandles() {
  if (!marketSymbol || !marketTimeframe) return;
  try {
    const hasChartEngine = initMarketChart();
    if (!hasChartEngine) scheduleTradingViewRetry();
    syncTradingViewSymbolAndInterval();
    const symbol = marketSymbol.value;
    const timeframe = marketTimeframe.value;
    const res = await fetch(`/api/market/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&limit=320`);
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    lastMarketSnapshot = data;
    const candles = data.candles || [];
    if (!candles.length) throw new Error('empty candles');
    if (tradingViewReady) {
      // TradingView widget renders the main chart; we only keep stats/status from API.
    } else if (marketFallbackMode || !marketSeries) {
      renderMarketFallback(candles);
    } else if (marketSeries) {
      marketSeries.setData(candles);
      marketVolumeSeries.setData(
        candles.map((c) => ({
          time: c.time,
          value: c.volume,
          color: c.close >= c.open ? '#2bc4b599' : '#ff5c6699',
        })),
      );
      if (marketFirstRender) {
        marketChart.timeScale().fitContent();
        marketFirstRender = false;
      }
    }
    renderMarketStats(data);
    const modeLabel = tradingViewReady ? 'tradingview' : (marketFallbackMode ? 'fallback-svg' : data.source);
    marketStatus.textContent = `${data.symbol} ${data.timeframe} • ${modeLabel} • ${new Date().toLocaleTimeString('pt-BR', { hour12: false })}`;
  } catch (err) {
    marketStatus.textContent = `Falha no market live: ${err.message}`;
  }
}

function applyLiveTradeToMarket(price) {
  const p = Number(price || 0);
  if (!p || !lastMarketSnapshot?.candles?.length) return;
  if (tradingViewReady) return;
  const candles = lastMarketSnapshot.candles;
  const last = candles[candles.length - 1];
  if (!last) return;
  last.close = p;
  last.high = Math.max(last.high, p);
  last.low = Math.min(last.low, p);
  if (marketFallbackMode) {
    renderMarketFallback(candles);
    return;
  }
  if (!marketSeries) return;
  const updated = {
    time: last.time,
    open: last.open,
    high: Math.max(last.high, p),
    low: Math.min(last.low, p),
    close: p,
  };
  marketSeries.update(updated);
  if (marketPriceLine) {
    marketSeries.removePriceLine(marketPriceLine);
  }
  marketPriceLine = marketSeries.createPriceLine({
    price: p,
    color: '#8fd8ff',
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true,
    title: 'LIVE',
  });
}

function connectMarketTickerWs() {
  if (!marketSymbol) return;
  const symbol = marketSymbol.value.toLowerCase();
  if (marketTickerReconnectTimer) {
    clearTimeout(marketTickerReconnectTimer);
    marketTickerReconnectTimer = null;
  }
  if (marketTickerWs) {
    marketTickerWs.onclose = null;
    marketTickerWs.close();
    marketTickerWs = null;
  }
  const wsUrl = `wss://stream.binance.com:9443/ws/${symbol}@trade`;
  try {
    marketTickerWs = new WebSocket(wsUrl);
    marketTickerWs.onopen = () => {
      marketTickerRetryAttempt = 0;
      if (marketStatus) {
        marketStatus.textContent = `${marketSymbol.value} ${marketTimeframe.value} • ws connected • ${new Date().toLocaleTimeString('pt-BR', { hour12: false })}`;
      }
    };
    marketTickerWs.onmessage = (evt) => {
      try {
        const payload = JSON.parse(evt.data);
        const px = Number(payload.p || 0);
        if (px > 0) {
          applyLiveTradeToMarket(px);
          if (marketStatus) {
            marketStatus.textContent = `${marketSymbol.value} ${marketTimeframe.value} • ws tick ${px.toLocaleString('en-US')} • ${new Date().toLocaleTimeString('pt-BR', { hour12: false })}`;
          }
        }
      } catch {
        // noop
      }
    };
    marketTickerWs.onclose = () => {
      const waitMs = Math.min(30000, 1000 * (2 ** Math.min(6, marketTickerRetryAttempt)));
      marketTickerRetryAttempt += 1;
      if (marketStatus) {
        marketStatus.textContent = `${marketSymbol.value} ${marketTimeframe.value} • ws reconnect in ${(waitMs / 1000).toFixed(0)}s (attempt ${marketTickerRetryAttempt})`;
      }
      marketTickerReconnectTimer = setTimeout(() => {
        if (!marketTickerWs || marketTickerWs.readyState === WebSocket.CLOSED) {
          connectMarketTickerWs();
        }
      }, waitMs);
    };
  } catch {
    // fallback silently to polling
  }
}

async function loadMarketDepth() {
  if (!marketSymbol) return;
  try {
    const symbol = marketSymbol.value;
    const res = await fetch(`/api/market/depth?symbol=${encodeURIComponent(symbol)}&limit=16`);
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    renderOrderBook(data);
    orderbookStatus.textContent = `${data.symbol} • ${data.source} • ${new Date().toLocaleTimeString('pt-BR', { hour12: false })}`;
  } catch (err) {
    orderbookStatus.textContent = `Falha no order book: ${err.message}`;
  }
}

async function loadMarketTrades() {
  if (!marketSymbol || !tradeTape) return;
  try {
    const symbol = marketSymbol.value;
    const res = await fetch(`/api/market/trades?symbol=${encodeURIComponent(symbol)}&limit=40`);
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    const rows = data.items || [];
    tradeTape.innerHTML = rows.map((r) => {
      const cls = r.is_sell ? 'sell' : 'buy';
      const side = r.is_sell ? 'SELL' : 'BUY';
      return `<div class="tape-row ${cls}"><span>${escapeHtml(fmtTime(r.timestamp * 1000))}</span><span class="px ${cls}">${escapeHtml(Number(r.price).toLocaleString('en-US'))}</span><span>${escapeHtml(Number(r.qty).toLocaleString('en-US', { maximumFractionDigits: 6 }))}</span><span>${side}</span></div>`;
    }).join('');
    tapeStatus.textContent = `${data.symbol} • ${data.source} • ${new Date().toLocaleTimeString('pt-BR', { hour12: false })}`;
  } catch (err) {
    tapeStatus.textContent = `Falha no tape: ${err.message}`;
  }
}

async function loadMarketDiagnostics() {
  if (!marketDiag || !marketDiagStatus) return;
  try {
    const res = await fetch('/api/market/diagnostics');
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    const items = Object.entries(data.items || {});
    updateBreakerPill(data.items || {});
    if (!items.length) {
      marketDiag.innerHTML = '<div class="muted-line">Sem métricas ainda.</div>';
    } else {
      marketDiag.innerHTML = items.slice(0, 6).map(([k, v]) => {
        const shortKey = String(k).replace('https://api.binance.com/api/v3/', '');
        const err = v.last_error ? ` | err: ${escapeHtml(v.last_error)}` : '';
        const breaker = v.breaker_open ? `breaker OPEN (${escapeHtml(v.breaker_open_until_s ?? '?')}s)` : 'breaker closed';
        return `<div class="tape-row"><span>${escapeHtml(shortKey)}</span><span>calls ${escapeHtml(v.calls)} / cache ${escapeHtml(v.cache_hits)} / stale ${escapeHtml(v.stale_served ?? 0)}</span><span>lat ${escapeHtml(v.last_latency_ms ?? '-')}ms (avg ${escapeHtml(v.avg_latency_ms ?? '-')} | p50 ${escapeHtml(v.p50_latency_ms ?? '-')} | p95 ${escapeHtml(v.p95_latency_ms ?? '-')})</span><span>errors ${escapeHtml(v.errors)} / streak ${escapeHtml(v.failure_streak ?? 0)} / ${breaker}${err}</span></div>`;
      }).join('');
    }
    marketDiagStatus.textContent = `cache ${data.cache_size} • ${new Date().toLocaleTimeString('pt-BR', { hour12: false })}`;
  } catch (err) {
    updateBreakerPill(null);
    marketDiagStatus.textContent = `Falha no diagnostics: ${err.message}`;
  }
}

function renderMetrics(overview) {
  currentOverview = overview;
  const cards = [
    ['Mode', overview.mode],
    ['Network', overview.network],
    ['Signals (total)', overview.total_signals],
    ['Trades (total)', overview.total_trades],
    ['Trades hoje', overview.trades_today],
    ['Execuções hoje', overview.executions_today],
  ];
  metricsRoot.innerHTML = cards
    .map(([label, value]) => `<div class="card"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`)
    .join('');
}

function renderSignals(rows) {
  signalsBody.innerHTML = rows.map((r) => (
    `<tr><td>${escapeHtml(fmtTime(r.timestamp))}</td><td>${escapeHtml(r.symbol)}</td><td>${escapeHtml(r.action)}</td><td>${escapeHtml(fmtPercent(r.confidence))}</td></tr>`
  )).join('');
}

function renderTrades(rows) {
  tradesBody.innerHTML = rows.map((r) => (
    `<tr><td>${escapeHtml(fmtTime(r.timestamp))}</td><td>${escapeHtml(r.symbol)}</td><td>${escapeHtml(r.status)}</td><td>${escapeHtml(fmtMoney(r.notional_usd))}</td></tr>`
  )).join('');
}

function renderAudit(rows) {
  auditLog.innerHTML = rows.map((r) => {
    const warn = r.severity !== 'INFO' && r.severity !== 'DEBUG' ? 'warn' : '';
    return `<div class="log-row ${warn}"><span class="time">${escapeHtml(fmtTime(r.timestamp))}</span><span class="agent">${escapeHtml(r.agent)}</span>${escapeHtml(r.event)} — ${escapeHtml(r.message || '')}</div>`;
  }).join('');
}

function renderLayers(layers) {
  if (!layers || !layers.items) {
    layerMap.innerHTML = '';
    sceneAlertLevel = 'normal';
    return;
  }
  const entries = Object.entries(layers.items);
  let hasWarning = false;
  let hasCritical = false;
  layerMap.innerHTML = entries.map(([code, layer]) => {
    const chips = (layer.heroes || []).map((h) => {
      if (h.status === 'warning') hasWarning = true;
      if (h.status === 'critical') hasCritical = true;
      return `<span class="hero-chip ${escapeHtml(h.status)}" title="${escapeHtml(h.event)}">${escapeHtml(h.hero)}</span>`;
    }).join('');
    return `<div class="layer-box"><h3>${escapeHtml(code)} • ${escapeHtml(layer.label)}</h3>${chips}</div>`;
  }).join('');
  sceneAlertLevel = hasCritical ? 'critical' : (hasWarning ? 'warning' : 'normal');
}

function renderTimeline(rows) {
  timelineRoot.innerHTML = (rows || []).map((r) => {
    const cls = r.severity === 'WARNING' ? 'warning' : (r.severity === 'ERROR' || r.severity === 'CRITICAL' ? 'critical' : '');
    return `<div class="timeline-row ${cls}"><span>${escapeHtml(fmtTime(r.timestamp))}</span><span class="event">${escapeHtml(r.event)}</span><span>${escapeHtml(r.message || '')}</span></div>`;
  }).join('');
}

function renderSymbolTimeline(rows) {
  symbolTimeline.innerHTML = (rows || []).map((r) => {
    const chips = (r.steps || []).map((s) => `<span class="step-chip">${escapeHtml(s.agent)}:${escapeHtml(s.event)}</span>`).join('');
    return `<div class="symbol-row"><strong>${escapeHtml(r.symbol)}</strong> • ${escapeHtml(r.duration_seconds)}s • ${escapeHtml(fmtTime(r.last_at))}<div>${chips}</div></div>`;
  }).join('');
}

function renderRiskHeatmap(rows) {
  riskHeatmap.innerHTML = (rows || []).map((r) => {
    return `<div class="risk-cell"><strong>${escapeHtml(r.symbol)}</strong><div class="risk-bars">
      <div class="risk-bar approved">A ${escapeHtml(r.approved)}</div>
      <div class="risk-bar reduced">R ${escapeHtml(r.reduced)}</div>
      <div class="risk-bar rejected">X ${escapeHtml(r.rejected)}</div>
      <div class="risk-bar kill">K ${escapeHtml(r.kill_switch)}</div>
    </div><button type="button" data-symbol="${escapeHtml(r.symbol)}" class="open-drill">Ver detalhes</button></div>`;
  }).join('');

  riskHeatmap.querySelectorAll('.open-drill').forEach((btn) => {
    btn.addEventListener('click', () => {
      openRiskDrilldown(btn.dataset.symbol || '');
    });
  });
}

function renderAnomalies(rows) {
  anomalyConsole.innerHTML = (rows || []).map((r) => {
    const sev = String(r.severity || '').toLowerCase();
    const sevClass = sev.includes('high') || sev.includes('critical') ? 'high' : (sev.includes('medium') ? 'medium' : '');
    const pauseClass = r.should_pause ? 'pause' : '';
    return `<div class="anomaly-row ${pauseClass}"><span>${escapeHtml(fmtTime(r.timestamp))}</span><span class="anomaly-sev ${sevClass}">${escapeHtml(r.severity)}</span><span>${escapeHtml(r.symbol || '-')}</span> ${escapeHtml(r.event)} ${r.should_pause ? '[PAUSE]' : ''} — ${escapeHtml(r.message || '')}</div>`;
  }).join('');
}

function renderHeroSla(rows) {
  heroSla.innerHTML = (rows || []).map((r) => {
    const avg = r.avg_seconds == null ? '-' : r.avg_seconds;
    const p95 = r.p95_seconds == null ? '-' : r.p95_seconds;
    return `<div class="sla-row"><strong>${escapeHtml(r.hero)}</strong>AVG: ${escapeHtml(avg)}s • P95: ${escapeHtml(p95)}s • n=${escapeHtml(r.samples)}</div>`;
  }).join('');
}

function renderGlobalAlerts(rows) {
  hasGlobalCriticalAlert = false;
  if (!rows || rows.length === 0) {
    globalAlerts.innerHTML = '';
    return;
  }
  globalAlerts.innerHTML = rows.map((r) => {
    if (String(r.severity || '').toUpperCase() === 'CRITICAL') hasGlobalCriticalAlert = true;
    const cls = String(r.severity || '').toUpperCase() === 'WARNING' ? 'warning' : '';
    return `<div class="alert-banner ${cls}">${escapeHtml(r.code)}: ${escapeHtml(r.message)}</div>`;
  }).join('');
}

function openRiskDrilldown(symbol) {
  const rows = currentRiskDrilldown[symbol] || [];
  riskModalTitle.textContent = `Batman Drilldown • ${symbol}`;
  riskModalBody.innerHTML = rows.map((r) => {
    const reasons = (r.reasons || []).length ? r.reasons.map(escapeHtml).join(', ') : '-';
    const breached = (r.breached_limits || []).length ? r.breached_limits.map(escapeHtml).join(', ') : '-';
    return `<div class="drill-row"><span class="drill-meta">${escapeHtml(fmtTime(r.timestamp))} ${escapeHtml(r.event)}</span>${escapeHtml(r.message || '')}<br/>Reasons: ${reasons}<br/>Breached: ${breached}</div>`;
  }).join('') || '<div class="drill-row">Sem detalhes.</div>';
  riskModal.classList.remove('hidden');
}

function closeRiskDrilldown() {
  riskModal.classList.add('hidden');
}

function applyFilters(payload) {
  const symbol = (filterSymbol.value || '').trim();
  const hero = (filterHero.value || '').trim();
  const event = (filterEvent.value || '').trim();
  const matchSym = (s) => _filterMatches(s, symbol);
  const matchHero = (s) => _filterMatches(s, hero);
  const matchEvent = (s) => _filterMatches(s, event);

  const signals = (payload.signals || []).filter((r) => matchSym(r.symbol));
  const trades = (payload.trades || []).filter((r) => matchSym(r.symbol));
  const audit = (payload.audit || []).filter((r) => {
    const symbolOk = matchSym(r.symbol) || (symbol ? _filterMatches(r.message, symbol) : true);
    return matchHero(r.agent) && matchEvent(r.event) && symbolOk;
  });
  const timeline = (payload.timeline || []).filter((r) => {
    const symbolOk = matchSym(r.symbol) || (symbol ? _filterMatches(r.message, symbol) : true);
    return matchEvent(r.event) && symbolOk;
  });
  const heatmap = (payload.risk_heatmap || []).filter((r) => matchSym(r.symbol));
  const symbols = (payload.symbol_timeline || []).filter((r) => matchSym(r.symbol));
  const anomalies = (payload.anomalies || []).filter((r) => {
    const symbolOk = matchSym(r.symbol) || (symbol ? _filterMatches(r.message, symbol) : true);
    return matchEvent(r.event) && symbolOk;
  });
  const sla = payload.hero_sla || [];

  renderSignals(signals);
  renderTrades(trades);
  renderAudit(audit);
  renderTimeline(timeline);
  renderSymbolTimeline(symbols);
  currentRiskDrilldown = payload.risk_drilldown || {};
  renderRiskHeatmap(heatmap);
  renderAnomalies(anomalies);
  renderHeroSla(sla);
  renderGlobalAlerts(payload.global_alerts || []);
  renderLayers(payload.layers || null);
}

function bindFilterEvents() {
  [filterSymbol, filterHero, filterEvent].forEach((el) => {
    el.addEventListener('input', () => {
      savePrefs({
        filterSymbol: filterSymbol?.value || '',
        filterHero: filterHero?.value || '',
        filterEvent: filterEvent?.value || '',
      });
      if (lastPayload) applyFilters(lastPayload);
    });
  });
}

function iso(x, y, z, scale = 18) {
  return {
    x: (x - y) * scale,
    y: (x + y) * scale * 0.5 - z * scale,
  };
}

function cube(x, y, z, w, h, d, color) {
  const p = [
    iso(x, y, z),
    iso(x + w, y, z),
    iso(x + w, y + h, z),
    iso(x, y + h, z),
    iso(x, y, z + d),
    iso(x + w, y, z + d),
    iso(x + w, y + h, z + d),
    iso(x, y + h, z + d),
  ];

  const cx = canvas.width * 0.5;
  const cy = canvas.height * 0.7;

  function drawFace(indexes, shade) {
    ctx.beginPath();
    indexes.forEach((idx, i) => {
      const pt = p[idx];
      if (i === 0) ctx.moveTo(cx + pt.x, cy + pt.y);
      else ctx.lineTo(cx + pt.x, cy + pt.y);
    });
    ctx.closePath();
    ctx.fillStyle = shade;
    ctx.fill();
    ctx.strokeStyle = 'rgba(15,22,40,0.6)';
    ctx.stroke();
  }

  drawFace([0, 1, 2, 3], color.top);
  drawFace([1, 5, 6, 2], color.right);
  drawFace([0, 4, 5, 1], color.left);
}

function drawPixelAgentSprite(agentIndex, x, y, z, px = 3) {
  const palette = AGENT_PALETTES[agentIndex % AGENT_PALETTES.length][1];
  const anchor = iso(x, y, z);
  const cx = canvas.width * 0.5 + anchor.x;
  const cy = canvas.height * 0.7 + anchor.y;

  for (let row = 0; row < SPRITE_PATTERN.length; row += 1) {
    const line = SPRITE_PATTERN[row];
    for (let col = 0; col < line.length; col += 1) {
      const k = line[col];
      if (k === '.') continue;
      const c = palette[k] || '#999';
      ctx.fillStyle = c;
      ctx.fillRect(
        Math.round(cx + col * px - (SPRITE_PATTERN[0].length * px * 0.5)),
        Math.round(cy + row * px - (SPRITE_PATTERN.length * px)),
        px,
        px,
      );
    }
  }
  // subtle ground shadow for depth readability
  ctx.fillStyle = 'rgba(6, 10, 18, 0.45)';
  ctx.fillRect(
    Math.round(cx - px * 4),
    Math.round(cy + 2),
    px * 8,
    px * 1.3,
  );
}

function renderScene() {
  tick += 1;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  let pulse = 0.65 + Math.sin(tick * 0.03) * 0.35;
  let floorTop = '#243252';
  const effectiveAlert = hasGlobalCriticalAlert ? 'critical' : sceneAlertLevel;
  if (effectiveAlert === 'warning') {
    pulse = 0.8 + Math.sin(tick * 0.05) * 0.5;
    floorTop = '#3a3022';
  }
  if (effectiveAlert === 'critical') {
    pulse = 1.0 + Math.sin(tick * 0.08) * 0.8;
    floorTop = '#4a1f24';
  }
  const screens = Math.max(1, currentOverview ? currentOverview.executions_today : 1);

  cube(-8, -8, 0, 16, 16, 0.2, { top: floorTop, right: '#17223b', left: '#1f2b47' });
  cube(-6, -4, 0.2, 2.8, 1.2, 1.2, { top: '#415886', right: '#2b3f66', left: '#364d79' });
  cube(-2.2, -4, 0.2, 2.8, 1.2, 1.2, { top: '#415886', right: '#2b3f66', left: '#364d79' });
  cube(1.6, -4, 0.2, 2.8, 1.2, 1.2, { top: '#415886', right: '#2b3f66', left: '#364d79' });

  for (let i = 0; i < Math.min(screens, 6); i += 1) {
    const x = -6 + i * 2.1;
    const glow = Math.floor(120 + 120 * pulse);
    cube(x, -2.4, 1.4, 1.6, 0.3, 1.2, {
      top: `rgb(${40 + i * 10}, ${glow}, 255)`,
      right: '#2f446d',
      left: '#24385d',
    });
  }

  const move = Math.sin(tick * 0.06) * 0.8;
  cube(-1.1 + move, 1.6, 0.2, 1.0, 1.0, 1.6, { top: '#ffbe55', right: '#c3842d', left: '#e19f3f' });
  cube(-1.1 + move, 1.6, 1.8, 1.0, 1.0, 0.7, { top: '#ffe4c5', right: '#f0cfa8', left: '#f8daba' });

  // Agents in the office (visible pixel sprites layered after geometry).
  // Layout approximates workstations and command lanes.
  const bob = Math.sin(tick * 0.08) * 0.06;
  const heroSpots = [
    [-5.2, -3.0, 1.3], [-3.1, -3.0, 1.3], [-1.0, -3.0, 1.3], [1.1, -3.0, 1.3],
    [3.2, -3.0, 1.3], [-4.2, -1.2, 1.3], [-2.1, -1.2, 1.3], [0.0, -1.2, 1.3],
    [2.1, -1.2, 1.3], [4.2, -1.2, 1.3], [-1.2, 1.8, 2.0], [0.0, 1.8, 2.0],
    [1.2, 1.8, 2.0],
  ];
  heroSpots.forEach((spot, idx) => {
    const [sx, sy, sz] = spot;
    drawPixelAgentSprite(idx, sx, sy, sz + ((idx % 2 === 0) ? bob : -bob), 3);
  });

  requestAnimationFrame(renderScene);
}

// ---------------------------------------------------------------------------
// Equity & PnL panel
// ---------------------------------------------------------------------------
function fmtMoneyDelta(v) {
  const n = Number(v || 0);
  const formatted = Math.abs(n).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  });
  return n >= 0 ? `+${formatted}` : `-${formatted}`;
}

function fmtPercentDelta(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return '-';
  const pct = (n * 100).toFixed(2);
  return n >= 0 ? `+${pct}%` : `${pct}%`;
}

function pnlPosNegClass(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return '';
  return n > 0 ? 'pos' : 'neg';
}

function renderPnlCards(summary) {
  if (!pnlCards) return;
  if (!summary) {
    pnlCards.innerHTML = '<div class="muted-line">Sem dados de PnL ainda.</div>';
    return;
  }
  const w = summary.window || {};
  const a = summary.all_time || {};
  const winRateW = w.win_rate == null ? '-' : `${(w.win_rate * 100).toFixed(1)}%`;
  const winRateA = a.win_rate == null ? '-' : `${(a.win_rate * 100).toFixed(1)}%`;
  const cards = [
    {
      label: `PnL ${summary.window_days}d`,
      value: fmtMoneyDelta(w.pnl_usd),
      sub: `${w.trades || 0} trades · ${w.days_with_data || 0} dias`,
      cls: pnlPosNegClass(w.pnl_usd),
    },
    {
      label: 'PnL all-time',
      value: fmtMoneyDelta(a.pnl_usd),
      sub: `${a.trades || 0} trades · ${a.trading_days || 0} dias`,
      cls: pnlPosNegClass(a.pnl_usd),
    },
    {
      label: 'Win rate',
      value: winRateW,
      sub: `all-time ${winRateA}`,
      cls: '',
    },
    {
      label: 'Max drawdown',
      value: `${(Number(w.max_drawdown_pct || 0) * 100).toFixed(2)}%`,
      sub: `equity ${Number(w.latest_equity_usd || 0).toLocaleString('en-US', {style: 'currency', currency: 'USD', maximumFractionDigits: 0})}`,
      cls: 'neg',
    },
  ];
  pnlCards.innerHTML = cards.map((c) => (
    `<div class="pnl-card">
       <span class="pnl-label">${escapeHtml(c.label)}</span>
       <span class="pnl-value ${c.cls}">${escapeHtml(c.value)}</span>
       <span class="pnl-sub">${escapeHtml(c.sub)}</span>
     </div>`
  )).join('');
}

function ensureBarChart(key, label, color) {
  if (!chartCanvases[key]) return null;
  if (typeof Chart === 'undefined') return null;
  if (chartInstances[key]) return chartInstances[key];
  chartInstances[key] = new Chart(chartCanvases[key], {
    type: 'bar',
    data: { labels: [], datasets: [{
      label,
      data: [],
      backgroundColor: color,
      borderWidth: 0,
    }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#95a3c4', maxTicksLimit: 8 }, grid: { color: 'rgba(72,151,255,0.06)' } },
        y: { ticks: { color: '#95a3c4' }, grid: { color: 'rgba(72,151,255,0.08)' } },
      },
    },
  });
  return chartInstances[key];
}

async function loadBenchmarkOverlay(days) {
  // Pulls one (or more) normalized close-to-close benchmarks from the
  // server and overlays them on a dedicated chart. Returns silently if
  // the chart canvas isn't on this page.
  if (typeof Chart === 'undefined' || !chartCanvases.benchmark) return;
  try {
    const res = await fetch(`/api/pnl/benchmark?days=${encodeURIComponent(days)}&symbols=BTC`, {
      cache: 'no-store',
    });
    if (!res.ok) return;
    const data = await res.json();
    const series = (data.series || [])[0];
    if (!series || !series.points || !series.points.length) return;
    const labels = series.points.map((p) => p.date_utc);
    const values = series.points.map((p) => p.ratio);
    const chart = ensureLineChart('benchmark', series.symbol, 'rgba(255, 191, 87, 1)');
    if (!chart) return;
    chart.data.labels = labels;
    chart.data.datasets[0].data = values;
    chart.data.datasets[0].label = `${series.symbol} (norm.)`;
    chart.update();
  } catch (_) { /* swallow — benchmark is best-effort */ }
}

async function loadTradesTimeline() {
  if (typeof Chart === 'undefined' || !chartCanvases.trades_timeline) return;
  const hours = Number(tradesTimelineHours?.value || 24) || 24;
  try {
    const res = await fetch(`/api/trades/timeline?hours=${encodeURIComponent(hours)}`, {
      cache: 'no-store',
    });
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    const items = data.items || [];
    if (!items.length) {
      if (tradesTimelineStatus) tradesTimelineStatus.textContent = 'Sem trades nesse intervalo.';
    }
    const labels = items.map((it) => {
      const d = new Date(it.hour_utc);
      return Number.isNaN(d.getTime())
        ? it.hour_utc
        : d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    });
    // Preserve canvas instance so the chart updates instead of re-mounting.
    if (chartInstances.trades_timeline) chartInstances.trades_timeline.destroy();
    chartInstances.trades_timeline = new Chart(chartCanvases.trades_timeline, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Filled', data: items.map((it) => it.filled || 0), backgroundColor: 'rgba(73, 209, 122, 0.85)' },
          { label: 'Paper',  data: items.map((it) => it.paper  || 0), backgroundColor: 'rgba(69, 208, 255, 0.6)'  },
          { label: 'Skipped', data: items.map((it) => it.skipped || 0), backgroundColor: 'rgba(149, 163, 196, 0.6)' },
          { label: 'Rejected', data: items.map((it) => it.rejected || 0), backgroundColor: 'rgba(255, 143, 87, 0.85)' },
          { label: 'Error',  data: items.map((it) => it.error  || 0), backgroundColor: 'rgba(255, 110, 110, 0.85)' },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { labels: { color: '#cfe4ff', boxWidth: 12 } } },
        scales: {
          x: { stacked: true, ticks: { color: '#95a3c4', maxTicksLimit: 12 }, grid: { color: 'rgba(72,151,255,0.06)' } },
          y: { stacked: true, ticks: { color: '#95a3c4', precision: 0 }, grid: { color: 'rgba(72,151,255,0.08)' }, beginAtZero: true },
        },
      },
    });
    if (tradesTimelineStatus) {
      tradesTimelineStatus.textContent = `${items.length} horas · ${new Date().toLocaleTimeString('pt-BR', { hour12: false })}`;
    }
  } catch (err) {
    if (tradesTimelineStatus) tradesTimelineStatus.textContent = `Falha: ${err && err.message ? err.message : err}`;
  }
}

let tradesTimelineAutoRefreshTimer = null;
function bootTradesTimeline() {
  loadTradesTimeline();
  tradesTimelineAutoRefreshTimer = _clearTimer(tradesTimelineAutoRefreshTimer);
  if (!document.hidden) {
    tradesTimelineAutoRefreshTimer = setInterval(loadTradesTimeline, 30000);
  }
}

async function loadPnl() {
  if (typeof Chart === 'undefined') {
    if (pnlStatus) pnlStatus.textContent = 'Chart.js indisponível.';
    return;
  }
  const days = Number(pnlWindowSelect?.value || 30) || 30;
  try {
    const [seriesRes, summaryRes] = await Promise.all([
      fetch(`/api/pnl/series?days=${encodeURIComponent(days)}`),
      fetch(`/api/pnl/summary?days=${encodeURIComponent(days)}`),
    ]);
    if (!seriesRes.ok) throw new Error('series ' + seriesRes.status);
    if (!summaryRes.ok) throw new Error('summary ' + summaryRes.status);
    const series = await seriesRes.json();
    const summary = await summaryRes.json();
    renderPnlCards(summary);

    const items = series.items || [];
    if (!items.length) {
      if (pnlStatus) pnlStatus.textContent = 'Sem dias de PnL persistidos ainda.';
      return;
    }
    const labels = items.map((it) => String(it.date_utc || ''));
    const equity = items.map((it) => Number(it.ending_equity || 0));
    const daily = items.map((it) => Number(it.pnl_usd || 0));
    const drawdown = items.map((it) => Number((it.drawdown_pct || 0) * 100));

    const equityChart = ensureLineChart('equity', 'Equity', 'rgba(73, 209, 122, 1)');
    const ddChart = ensureLineChart('drawdown', 'Drawdown %', 'rgba(255, 110, 110, 1)');
    const dailyChart = ensureBarChart(
      'daily_pnl', 'Daily PnL', 'rgba(69, 208, 255, 0.7)',
    );

    if (equityChart) {
      equityChart.data.labels = labels;
      equityChart.data.datasets[0].data = equity;
      equityChart.update();
    }
    if (ddChart) {
      ddChart.data.labels = labels;
      ddChart.data.datasets[0].data = drawdown;
      ddChart.update();
    }
    if (dailyChart) {
      dailyChart.data.labels = labels;
      dailyChart.data.datasets[0].data = daily;
      // Per-bar colour so positive days are green, negative are red.
      dailyChart.data.datasets[0].backgroundColor = daily.map(
        (v) => (v >= 0 ? 'rgba(73, 209, 122, 0.7)' : 'rgba(255, 110, 110, 0.7)'),
      );
      dailyChart.update();
    }
    if (pnlStatus) {
      pnlStatus.textContent = `${items.length} dias · janela ${days}d · ${new Date().toLocaleTimeString('pt-BR', { hour12: false })}`;
    }
    // Benchmark overlay rides on the same window — best-effort, never
    // blocks the PnL render even if the market provider is unhappy.
    loadBenchmarkOverlay(days);
  } catch (err) {
    if (pnlStatus) pnlStatus.textContent = `Falha no PnL: ${err && err.message ? err.message : err}`;
  }
}

// ---------------------------------------------------------------------------
// Auth — three-mode: anonymous (dev), shared-secret (legacy header), session
// cookie. Cookie path is preferred when MEKKA_DASHBOARD_PASSWORD is set on
// the server. Legacy header is still accepted as fallback.
// ---------------------------------------------------------------------------
const KS_TOKEN_KEY = 'mekka_dashboard_token_v1';
function getDashboardToken() {
  try { return sessionStorage.getItem(KS_TOKEN_KEY) || ''; } catch { return ''; }
}
function setDashboardToken(value) {
  try { sessionStorage.setItem(KS_TOKEN_KEY, value || ''); } catch { /* noop */ }
}

let _authState = {
  authenticated: false,
  expires_at: null,
  subject: null,
  login_enabled: false,
  shared_secret_enabled: false,
};

function renderAuthState() {
  if (!authButton || !authState) return;
  if (_authState.authenticated) {
    authButton.textContent = 'Logout';
    authState.className = 'auth-state authed';
    const exp = _authState.expires_at
      ? new Date(_authState.expires_at * 1000).toLocaleTimeString('pt-BR', { hour12: false })
      : '';
    authState.textContent = exp ? `${_authState.subject || 'op'} · até ${exp}` : (_authState.subject || 'op');
  } else if (_authState.login_enabled) {
    authButton.textContent = 'Login';
    authState.className = 'auth-state anon';
    authState.textContent = 'sem sessão';
  } else if (_authState.shared_secret_enabled) {
    authButton.textContent = 'Set Token';
    authState.className = 'auth-state anon';
    authState.textContent = 'shared-secret';
  } else {
    authButton.textContent = 'Auth';
    authState.className = 'auth-state';
    authState.textContent = 'sem auth (dev)';
  }
}

async function refreshAuthState() {
  try {
    const res = await fetch('/api/auth/me', { cache: 'no-store', credentials: 'include' });
    if (!res.ok) return;
    _authState = await res.json();
    renderAuthState();
  } catch (_) { /* swallow */ }
}

function openAuthModal() {
  if (!_authState.login_enabled) {
    // Fall back to the legacy shared-secret prompt if password login isn't
    // configured but a token still is — keeps CI scripts working.
    if (_authState.shared_secret_enabled) return promptForLegacyToken();
    return; // no auth at all on the server
  }
  if (authError) authError.textContent = '';
  if (authPassword) authPassword.value = '';
  if (authModal) authModal.classList.remove('hidden');
  setTimeout(() => { try { authPassword?.focus(); } catch {} }, 0);
}

function closeAuthModal() {
  if (authModal) authModal.classList.add('hidden');
}

async function submitAuthLogin() {
  const password = String(authPassword?.value || '');
  if (!password) {
    if (authError) authError.textContent = 'Senha vazia.';
    return;
  }
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ password }),
    });
    if (res.status === 401) {
      if (authError) authError.textContent = 'Senha incorreta.';
      return;
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      if (authError) authError.textContent = `Falha (${res.status}): ${data.error || 'unknown'}`;
      return;
    }
    closeAuthModal();
    await refreshAuthState();
  } catch (err) {
    if (authError) authError.textContent = `Erro de rede: ${err && err.message ? err.message : err}`;
  }
}

async function logoutAuth() {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST', credentials: 'include',
    });
  } catch (_) { /* ignore */ }
  await refreshAuthState();
}

function promptForLegacyToken() {
  const current = getDashboardToken();
  const next = window.prompt(
    'Shared-secret mode: cole o token configurado em MEKKA_DASHBOARD_TOKEN (vazio = limpar).',
    current,
  );
  if (next === null) return;
  setDashboardToken(next.trim());
  renderAuthState();
}

async function refreshKillswitchStatus() {
  if (!killswitchStatus) return;
  try {
    const res = await fetch('/api/killswitch/status', { cache: 'no-store' });
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    if (data.active) {
      const reason = data.reason ? ` · motivo: ${data.reason}` : '';
      const ts = data.mtime_utc ? ` · desde ${data.mtime_utc}` : '';
      killswitchStatus.innerHTML = `
        <span class="killswitch-state-active">ATIVO</span>${escapeHtml(reason)}${escapeHtml(ts)}
      `;
      if (killswitchEngageBtn) killswitchEngageBtn.disabled = true;
      if (killswitchReleaseBtn) killswitchReleaseBtn.disabled = false;
    } else {
      killswitchStatus.innerHTML = `<span class="killswitch-state-clear">SEM kill switch</span>`;
      if (killswitchEngageBtn) killswitchEngageBtn.disabled = false;
      if (killswitchReleaseBtn) killswitchReleaseBtn.disabled = true;
    }
  } catch (err) {
    killswitchStatus.textContent = `Falha ao ler status: ${err && err.message ? err.message : err}`;
  }
}

function openKillswitchModal(action) {
  killswitchAction = action;
  const isEngage = action === 'engage';
  if (killswitchModalTitle) killswitchModalTitle.textContent = isEngage
    ? 'Confirmar ENGAGE do kill switch'
    : 'Confirmar RELEASE do kill switch';
  if (killswitchModalText) {
    killswitchModalText.textContent = isEngage
      ? 'Isso para imediatamente o ciclo de trading. Tem certeza?'
      : 'Isso libera o ciclo de trading. Confirme.';
  }
  if (killswitchModalConfirmLabel) {
    killswitchModalConfirmLabel.textContent = isEngage
      ? 'Digite ENGAGE para confirmar'
      : 'Digite RELEASE para confirmar';
  }
  if (killswitchModalReason) killswitchModalReason.value = '';
  if (killswitchModalConfirm) killswitchModalConfirm.value = '';
  if (killswitchModalError) killswitchModalError.textContent = '';
  if (killswitchModal) killswitchModal.classList.remove('hidden');
  setTimeout(() => { try { killswitchModalConfirm?.focus(); } catch {} }, 0);
}

function closeKillswitchModal() {
  if (killswitchModal) killswitchModal.classList.add('hidden');
  killswitchAction = null;
}

async function submitKillswitchAction() {
  if (!killswitchAction) return;
  const expected = killswitchAction === 'engage' ? 'ENGAGE' : 'RELEASE';
  const typed = String(killswitchModalConfirm?.value || '').trim().toUpperCase();
  if (typed !== expected) {
    if (killswitchModalError) {
      killswitchModalError.textContent = `Você precisa digitar exatamente "${expected}".`;
    }
    return;
  }
  const reason = String(killswitchModalReason?.value || '').trim();
  const url = killswitchAction === 'engage'
    ? '/api/killswitch/engage'
    : '/api/killswitch/release';
  const body = killswitchAction === 'engage'
    ? { confirm: 'ENGAGE', reason }
    : { confirm: 'RELEASE', operator: reason };
  try {
    const headers = { 'Content-Type': 'application/json' };
    const token = getDashboardToken();
    if (token) headers['X-Mekka-Token'] = token;
    const res = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: JSON.stringify(body),
    });
    if (res.status === 401) {
      if (killswitchModalError) {
        killswitchModalError.textContent = _authState.login_enabled
          ? 'Sessão necessária. Clique em "Login" no card e tente de novo.'
          : 'Servidor exigiu token. Clique em "Set Token" e cole o token configurado.';
      }
      // Refresh auth state so the next attempt knows whether we logged in.
      refreshAuthState();
      return;
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      if (killswitchModalError) {
        killswitchModalError.textContent = `Falha (${res.status}): ${data.error || 'unknown'}`;
      }
      return;
    }
    closeKillswitchModal();
    await refreshKillswitchStatus();
  } catch (err) {
    if (killswitchModalError) {
      killswitchModalError.textContent = `Erro de rede: ${err && err.message ? err.message : err}`;
    }
  }
}

// `promptForToken` was the single-shared-secret prompt; the new
// `openAuthModal` flow handles both modes (password login or legacy token).

function bootKillswitch() {
  refreshKillswitchStatus();
  killswitchAutoRefreshTimer = _clearTimer(killswitchAutoRefreshTimer);
  if (!document.hidden) {
    killswitchAutoRefreshTimer = setInterval(refreshKillswitchStatus, 5000);
  }
}

// ---------------------------------------------------------------------------
// Open positions
// ---------------------------------------------------------------------------
// Cadência de auto-refresh adaptativa: 3s quando o provider live (Hyperliquid)
// está respondendo, 30s no stub. Evita pressionar a API quando não há nada
// pra atualizar, mas mantém o painel live quase tempo-real.
let _positionsRefreshIntervalMs = 30000;
async function loadPositions() {
  if (!positionsBody) return;
  try {
    const res = await fetch('/api/positions', { cache: 'no-store' });
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    const isLive = data.source === 'hyperliquid' && data.supported;
    const tier = isLive ? 'pos-live' : 'pos-stub';
    if (positionsStatus) {
      const dot = isLive
        ? '<span class="pos-dot live" aria-label="live"></span>'
        : '<span class="pos-dot stub" aria-label="stub"></span>';
      positionsStatus.innerHTML = `${dot} ${escapeHtml(data.count || 0)} posições · ${escapeHtml(data.source || '-')}${data.message ? ' · ' + escapeHtml(data.message) : ''}`;
    }
    // Tune the auto-refresh cadence based on what the provider returned.
    const nextInterval = isLive ? 3000 : 30000;
    if (nextInterval !== _positionsRefreshIntervalMs) {
      _positionsRefreshIntervalMs = nextInterval;
      bootPositions();
    }
    const items = data.items || [];
    if (!items.length) {
      positionsBody.innerHTML = `<div class="positions-empty ${tier}">${escapeHtml(data.message || 'Sem posições abertas.')}</div>`;
      return;
    }
    const rows = items.map((p) => {
      const sideCls = String(p.side || '').toUpperCase() === 'SHORT' ? 'pos-side-short' : 'pos-side-long';
      const pnl = Number(p.pnl_usd || 0);
      const pnlCls = pnl > 0 ? 'pos-side-long' : (pnl < 0 ? 'pos-side-short' : '');
      const paperBadge = p.is_paper ? '<span class="pos-badge paper">PAPER</span>' : '';
      const closeBtn = p.is_paper
        ? `<button class="btn-close-pos" data-symbol="${escapeHtml(p.symbol)}" data-side="${escapeHtml(p.side)}" type="button">Fechar</button>`
        : '—';
      const symKey = String(p.symbol || '').toUpperCase();
      const sideKey = String(p.side || 'LONG').toUpperCase();
      return `
        <tr data-sym="${symKey}" data-side="${sideKey}">
          <td>${escapeHtml(p.symbol)} ${paperBadge}</td>
          <td class="${sideCls}">${escapeHtml(p.side)}</td>
          <td>${escapeHtml(p.size)}</td>
          <td>${escapeHtml(p.entry_price)}</td>
          <td class="col-mark">${escapeHtml(p.mark_price)}</td>
          <td class="col-pnl ${pnlCls}">${escapeHtml(fmtMoneyDelta(pnl))}</td>
          <td>${escapeHtml(p.leverage ?? '-')}${p.leverage ? 'x' : ''}</td>
          <td>${escapeHtml(p.liq_price ?? '-')}</td>
          <td>${closeBtn}</td>
        </tr>`;
    }).join('');
    positionsBody.innerHTML = `
      <table class="positions-table">
        <thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>Mark</th><th>PnL</th><th>Lev</th><th>Liq</th><th>Ação</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;

    // Wire up close buttons
    positionsBody.querySelectorAll('.btn-close-pos').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const sym = btn.dataset.symbol;
        const side = btn.dataset.side;
        if (!confirm(`Fechar posição ${sym} ${side}? Esta ação é irreversível em paper mode.`)) return;
        btn.disabled = true;
        btn.textContent = '…';
        try {
          const _closeHdrs = { 'Content-Type': 'application/json' };
          const _closeTok = getDashboardToken();
          if (_closeTok) _closeHdrs['X-Mekka-Token'] = _closeTok;
          const res = await fetch('/api/positions/close', {
            method: 'POST',
            headers: _closeHdrs,
            credentials: 'include',
            body: JSON.stringify({ symbol: sym, side }),
          });
          const data = await res.json();
          if (res.ok && data.status === 'closed') {
            btn.closest('tr').style.opacity = '0.35';
            btn.textContent = '✓ Fechado';
            setTimeout(loadPositions, 1200);  // refresh panel
          } else {
            alert('Erro ao fechar: ' + (data.error || JSON.stringify(data)));
            btn.disabled = false;
            btn.textContent = 'Fechar';
          }
        } catch (err) {
          alert('Falha na requisição: ' + err);
          btn.disabled = false;
          btn.textContent = 'Fechar';
        }
      });
    });
  } catch (err) {
    if (positionsStatus) positionsStatus.textContent = `Falha: ${err && err.message ? err.message : err}`;
    positionsBody.innerHTML = '<div class="positions-empty">Falha ao carregar posições.</div>';
  }
}

function bootPositions() {
  loadPositions();
  positionsAutoRefreshTimer = _clearTimer(positionsAutoRefreshTimer);
  if (!document.hidden) {
    positionsAutoRefreshTimer = setInterval(loadPositions, _positionsRefreshIntervalMs);
  }
}

// ---------------------------------------------------------------------------
// Funding Rates panel
// ---------------------------------------------------------------------------
const fundingRefreshBtn = document.getElementById('funding-refresh');
const fundingStatus    = document.getElementById('funding-status');
const fundingBody      = document.getElementById('funding-body');
const fundingAsOf      = document.getElementById('funding-as-of');

function _fundingRateCls(rate) {
  if (rate > 0.00005) return 'funding-rate-pos';
  if (rate < -0.00005) return 'funding-rate-neg';
  return 'funding-rate-zero';
}
function _sentimentBadge(sentiment) {
  const map = {
    bullish: '<span class="funding-bullish">↑ Bullish</span>',
    bearish: '<span class="funding-bearish">↓ Bearish</span>',
    neutral: '<span class="funding-neutral">→ Neutral</span>',
  };
  return map[sentiment] || '';
}

async function loadFundingRates() {
  if (!fundingBody) return;
  try {
    const res = await fetch('/api/market/funding', { cache: 'no-store' });
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();

    if (fundingStatus) {
      const src = escapeHtml(data.source_primary || '?');
      fundingStatus.textContent = `${data.count || 0} ativos · fonte: ${src}`;
    }
    if (fundingAsOf && data.as_of_utc) {
      const t = new Date(data.as_of_utc);
      fundingAsOf.textContent = `· atualizado ${t.toLocaleTimeString()}`;
    }

    const items = data.items || [];
    if (!items.length) {
      fundingBody.innerHTML = '<div class="positions-empty">Sem dados de funding.</div>';
      return;
    }

    const rows = items.map(item => {
      const rateCls = _fundingRateCls(item.funding_rate);
      const ratePct = Number(item.funding_pct || 0).toFixed(4);
      const annualPct = Number(item.annualized_pct || 0).toFixed(1);
      const markPx = item.mark_price ? '$' + Number(item.mark_price).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '—';
      const oi = item.open_interest
        ? '$' + (Number(item.open_interest) / 1e6).toFixed(1) + 'M'
        : '—';
      const srcBadge = `<span class="funding-source-badge">${escapeHtml(item.source)}</span>`;
      return `<tr>
        <td><strong>${escapeHtml(item.symbol)}</strong>${srcBadge}</td>
        <td class="${rateCls}">${ratePct}%</td>
        <td class="${rateCls}">${annualPct}%/yr</td>
        <td>${_sentimentBadge(item.sentiment)}</td>
        <td>${markPx}</td>
        <td class="muted-line">${oi}</td>
      </tr>`;
    }).join('');

    fundingBody.innerHTML = `
      <table class="funding-table">
        <thead><tr>
          <th>Ativo</th>
          <th>Rate 8h</th>
          <th>Anualizado</th>
          <th>Sentimento</th>
          <th>Mark Price</th>
          <th>Open Interest</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch (err) {
    if (fundingStatus) fundingStatus.textContent = `Falha: ${err && err.message ? err.message : err}`;
    fundingBody.innerHTML = '<div class="positions-empty">Falha ao carregar funding rates.</div>';
  }
}

let fundingAutoRefreshTimer = null;
function bootFunding() {
  loadFundingRates();
  fundingAutoRefreshTimer = _clearTimer(fundingAutoRefreshTimer);
  if (!document.hidden) {
    fundingAutoRefreshTimer = setInterval(loadFundingRates, 60000); // refresh 60s
  }
}

if (fundingRefreshBtn) fundingRefreshBtn.addEventListener('click', loadFundingRates);

// ---------------------------------------------------------------------------
// Internals (Prometheus /metrics consumed for the operator card view)
// ---------------------------------------------------------------------------
function parsePromMetrics(text) {
  // Minimal parser: returns { name -> value }. Skips HELP/TYPE comments and
  // lines that don't match the simple `name value` pattern. Good enough for
  // our self-hosted /metrics where labels aren't used.
  const out = {};
  for (const line of String(text || '').split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const idx = trimmed.lastIndexOf(' ');
    if (idx <= 0) continue;
    const name = trimmed.slice(0, idx).trim();
    const value = Number(trimmed.slice(idx + 1).trim());
    if (!name || !Number.isFinite(value)) continue;
    out[name] = value;
  }
  return out;
}

async function loadInternals() {
  if (!internalsCards) return;
  try {
    const res = await fetch('/metrics', { cache: 'no-store' });
    if (!res.ok) throw new Error('http ' + res.status);
    const text = await res.text();
    if (internalsRawPre) internalsRawPre.textContent = text;
    const m = parsePromMetrics(text);
    const cards = [
      {
        label: 'Active sockets',
        value: Math.round(m['mekka_ws_active_connections'] || 0),
        sub: `total accepted ${Math.round(m['mekka_ws_connections_total'] || 0)}`,
      },
      {
        label: 'Broadcasts',
        value: Math.round(m['mekka_broadcasts_total'] || 0),
        sub: `errors ${Math.round(m['mekka_broadcasts_errors_total'] || 0)} · slow drops ${Math.round(m['mekka_ws_slow_consumers_dropped_total'] || 0)}`,
        cls: (m['mekka_broadcasts_errors_total'] || 0) > 0 ? 'neg' : '',
      },
      {
        label: 'Payload latency p50/p95',
        value: `${(m['mekka_payload_collect_latency_ms_p50'] || 0).toFixed(0)} / ${(m['mekka_payload_collect_latency_ms_p95'] || 0).toFixed(0)} ms`,
        sub: `${Math.round(m['mekka_payload_collect_samples'] || 0)} amostras`,
      },
      {
        label: 'Cache hit rate',
        value: cacheHitRate(m),
        sub: `hits ${Math.round(m['mekka_payload_cache_hits_total'] || 0)} / miss ${Math.round(m['mekka_payload_cache_misses_total'] || 0)}`,
      },
      {
        label: 'Snapshots / Bundles',
        value: `${Math.round(m['mekka_snapshot_writes_total'] || 0)} / ${Math.round(m['mekka_incident_bundle_writes_total'] || 0)}`,
        sub: `kill engage ${Math.round(m['mekka_killswitch_engaged_total'] || 0)} · release ${Math.round(m['mekka_killswitch_released_total'] || 0)}`,
      },
      {
        label: 'Market breakers',
        value: Math.round(m['mekka_market_breakers_open'] || 0),
        sub: `cache ${Math.round(m['mekka_market_cache_size'] || 0)} entries`,
        cls: (m['mekka_market_breakers_open'] || 0) > 0 ? 'neg' : '',
      },
    ];
    internalsCards.innerHTML = cards.map((c) => (
      `<div class="pnl-card">
         <span class="pnl-label">${escapeHtml(c.label)}</span>
         <span class="pnl-value ${c.cls || ''}">${escapeHtml(c.value)}</span>
         <span class="pnl-sub">${escapeHtml(c.sub || '')}</span>
       </div>`
    )).join('');
    if (internalsStatus) internalsStatus.textContent = `Atualizado ${new Date().toLocaleTimeString('pt-BR', { hour12: false })}`;
  } catch (err) {
    if (internalsStatus) internalsStatus.textContent = `Falha: ${err && err.message ? err.message : err}`;
  }
}

function cacheHitRate(m) {
  const hits = m['mekka_payload_cache_hits_total'] || 0;
  const miss = m['mekka_payload_cache_misses_total'] || 0;
  const total = hits + miss;
  if (!total) return '-';
  return `${((hits / total) * 100).toFixed(1)}%`;
}

function bootInternals() {
  loadInternals();
  internalsAutoRefreshTimer = _clearTimer(internalsAutoRefreshTimer);
  if (!document.hidden) {
    internalsAutoRefreshTimer = setInterval(loadInternals, 5000);
  }
}

// ---------------------------------------------------------------------------
// Filter mode helper (exact / contains / prefix)
// ---------------------------------------------------------------------------
function _filterMatches(haystack, needle) {
  if (!needle) return true;
  const mode = (filterMode?.value || 'contains').toLowerCase();
  const h = String(haystack || '');
  if (mode === 'exact') return h.toUpperCase() === needle.toUpperCase();
  if (mode === 'prefix') return h.toUpperCase().startsWith(needle.toUpperCase());
  return h.toUpperCase().includes(needle.toUpperCase());
}

let _wsRetryAttempt = 0;
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    _wsRetryAttempt = 0;
    statusPill.textContent = 'Online';
    statusPill.style.color = '#49d17a';
  };

  ws.onclose = () => {
    // Exponential backoff with a 30s ceiling so a server outage doesn't
    // generate hundreds of useless reconnect attempts per minute.
    const wait = Math.min(30000, 1000 * (2 ** Math.min(6, _wsRetryAttempt)));
    _wsRetryAttempt += 1;
    statusPill.textContent = `Reconectando em ${(wait / 1000).toFixed(0)}s...`;
    statusPill.style.color = '#ff8f57';
    setTimeout(connect, wait);
  };

  ws.onerror = () => {
    // Force a clean close so onclose triggers the backoff path.
    try { ws.close(); } catch { /* noop */ }
  };

  ws.onmessage = (event) => {
    if (replayMode !== 'live') return;
    try {
      const payload = JSON.parse(event.data);
      lastPayload = payload;
      renderMetrics(payload.overview);
      applyFilters(payload);
    } catch (err) {
      console.warn('ws message parse failed', err);
    }
  };
}

function bindSidebarScrollSpy() {
  if (!sidebarAnchors.length) return;
  const sections = sidebarAnchors
    .map((a) => document.querySelector(a.getAttribute('href')))
    .filter(Boolean);
  if (!sections.length) return;
  const obs = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const id = '#' + entry.target.id;
      sidebarAnchors.forEach((a) => a.classList.toggle('active', a.getAttribute('href') === id));
    });
  }, { rootMargin: '-30% 0px -55% 0px', threshold: 0.01 });
  sections.forEach((s) => obs.observe(s));
}

async function refreshApiHealth() {
  try {
    const res = await fetch('/api/health');
    if (!res.ok) throw new Error('http ' + res.status);
    const d = await res.json();
    if (!d.ok) throw new Error('not ok');
    statusPill.title = `API ${d.mode} / ${String(d.network || '').toUpperCase()} / ${d.time_utc}`;
  } catch {
    statusPill.title = 'API health check falhou';
  }
}

async function loadReplaySnapshots() {
  try {
    const res = await fetch('/api/replay/snapshots');
    const data = await res.json();
    replaySnapshots = data.snapshots || [];
    replaySnapshotSelect.innerHTML = replaySnapshots.map((s, idx) => `<option value="${idx}">${escapeHtml(s)}</option>`).join('');
    compareA.innerHTML = replaySnapshots.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
    compareB.innerHTML = replaySnapshots.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
    if (replaySnapshots.length > 0) {
      replayIndex = 0;
      replaySnapshotSelect.value = '0';
      compareA.value = replaySnapshots[0];
      compareB.value = replaySnapshots[Math.min(1, replaySnapshots.length - 1)];
    }
  } catch {
    replaySnapshots = [];
    replaySnapshotSelect.innerHTML = '';
    compareA.innerHTML = '';
    compareB.innerHTML = '';
  }
}

async function loadIncidentBundles() {
  try {
    const res = await fetch('/api/replay/incidents');
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    const bundles = data.bundles || [];
    if (!bundles.length) {
      incidentBundleSelect.innerHTML = '<option value="">Sem bundles</option>';
      return;
    }
    incidentBundleSelect.innerHTML = bundles.map((b) => `<option value="${escapeHtml(b)}">${escapeHtml(b)}</option>`).join('');
  } catch {
    incidentBundleSelect.innerHTML = '<option value="">Falha ao carregar</option>';
  }
}

async function loadReplayByIndex(index) {
  if (index < 0 || index >= replaySnapshots.length) return;
  replayMode = 'replay';
  replayIndex = index;
  replaySnapshotSelect.value = String(index);
  const name = replaySnapshots[index];
  const res = await fetch(`/api/replay?snapshot=${encodeURIComponent(name)}`);
  if (!res.ok) return;
  const payload = await res.json();
  lastPayload = payload;
  // textContent is already safe (no HTML interpretation), no escapeHtml needed.
  replayStatus.textContent = `Replay: ${name}`;
  renderMetrics(payload.overview);
  applyFilters(payload);
}

function setLiveMode() {
  replayMode = 'live';
  replayStatus.textContent = 'Live stream ativo';
  if (replayTimer) {
    clearInterval(replayTimer);
    replayTimer = null;
    replayPlayBtn.textContent = 'Play';
  }
}

function toggleReplayPlay() {
  if (replayMode === 'live') return;
  if (replayTimer) {
    clearInterval(replayTimer);
    replayTimer = null;
    replayPlayBtn.textContent = 'Play';
    return;
  }
  replayPlayBtn.textContent = 'Pause';
  replayTimer = setInterval(() => {
    if (replayIndex + 1 >= replaySnapshots.length) {
      clearInterval(replayTimer);
      replayTimer = null;
      replayPlayBtn.textContent = 'Play';
      return;
    }
    loadReplayByIndex(replayIndex + 1);
  }, 1200);
}

function currentExportRange() {
  if (replaySnapshots.length === 0) return { start: null, end: null };
  const start = replaySnapshots[replaySnapshots.length - 1];
  const end = replaySnapshots[0];
  return { start, end };
}

function exportReplay(format) {
  const { start, end } = currentExportRange();
  if (!start || !end) return;
  const startUtc = (exportStartUtc.value || '').trim();
  const endUtc = (exportEndUtc.value || '').trim();
  let url = `/api/replay/export?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&format=${encodeURIComponent(format)}`;
  if (startUtc) url += `&start_utc=${encodeURIComponent(startUtc)}`;
  if (endUtc) url += `&end_utc=${encodeURIComponent(endUtc)}`;
  window.open(url, '_blank');
}

async function runCompare() {
  const a = compareA.value;
  const b = compareB.value;
  if (!a || !b) return;
  const res = await fetch(`/api/replay/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  if (!res.ok) {
    compareOutput.textContent = 'Falha na comparação.';
    return;
  }
  const d = await res.json();
  const ov = d.overview_delta || {};
  const riskRows = (d.risk_delta || []).map((r) => `<tr><td>${escapeHtml(r.symbol)}</td><td>${escapeHtml(r.approved)}</td><td>${escapeHtml(r.reduced)}</td><td>${escapeHtml(r.rejected)}</td><td>${escapeHtml(r.kill_switch)}</td></tr>`).join('');
  const slaRows = (d.sla_delta || []).map((s) => `<tr><td>${escapeHtml(s.hero)}</td><td>${escapeHtml(s.avg_seconds_delta)}</td><td>${escapeHtml(s.samples_delta)}</td></tr>`).join('');
  const alertsAdded = (d.alerts_added || []).map((x) => `<div>+ ${escapeHtml(x)}</div>`).join('') || '<div>-</div>';
  const alertsRemoved = (d.alerts_removed || []).map((x) => `<div>- ${escapeHtml(x)}</div>`).join('') || '<div>-</div>';
  compareOutput.innerHTML = `
    <div><strong>${escapeHtml(d.snapshot_a)}</strong> vs <strong>${escapeHtml(d.snapshot_b)}</strong></div>
    <div>Overview Δ: signals ${escapeHtml(ov.total_signals)}, trades ${escapeHtml(ov.total_trades)}, trades_today ${escapeHtml(ov.trades_today)}, exec_today ${escapeHtml(ov.executions_today)}</div>
    <div>Alerts Added</div>${alertsAdded}
    <div>Alerts Removed</div>${alertsRemoved}
    <table class="compare-table"><thead><tr><th>Symbol</th><th>ΔApproved</th><th>ΔReduced</th><th>ΔRejected</th><th>ΔKill</th></tr></thead><tbody>${riskRows}</tbody></table>
    <table class="compare-table"><thead><tr><th>Hero</th><th>ΔAvg(s)</th><th>ΔSamples</th></tr></thead><tbody>${slaRows}</tbody></table>
  `;
}

function triggerDownload(url, suggestedName) {
  // Programmatic <a download> beats window.location.href because some
  // browsers (and PWAs / extensions) ignore Content-Disposition and navigate
  // the whole tab — losing the dashboard state. The hidden anchor approach
  // always saves the file and never disrupts the page.
  const anchor = document.createElement('a');
  anchor.href = url;
  if (suggestedName) anchor.download = suggestedName;
  anchor.rel = 'noopener';
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  setTimeout(() => anchor.remove(), 0);
}

function downloadIncidentBundle() {
  triggerDownload('/api/replay/incident/latest/download', 'incident-bundle.json');
}

function downloadSelectedIncidentBundle() {
  const name = incidentBundleSelect.value;
  if (!name) return;
  triggerDownload(`/api/replay/incident/download?name=${encodeURIComponent(name)}`, name);
}

function severityClass(tier) {
  const t = String(tier || '').toUpperCase();
  if (t === 'CRITICAL') return 'sev-critical';
  if (t === 'HIGH') return 'sev-high';
  if (t === 'MEDIUM') return 'sev-medium';
  if (t === 'LOW') return 'sev-low';
  return 'sev-none';
}

function renderIncidentDetail(item) {
  if (!incidentQueueDetail) return;
  if (!item) {
    incidentQueueDetail.innerHTML = 'Selecione um incidente para ver detalhes rápidos de investigação.';
    return;
  }
  const alerts = (item.alerts || []).slice(0, 6);
  const alertHtml = alerts.length
    ? alerts.map((a) => `<li><strong>${escapeHtml(a.code || 'ALERT')}</strong>: ${escapeHtml(a.message || '-')}</li>`).join('')
    : '<li>Sem alertas detalhados nesse snapshot.</li>';
  const drivers = item.drivers || {};
  incidentQueueDetail.innerHTML = `
    <div><strong>Incident Detail</strong> | ${escapeHtml(fmtSnapshotLabel(item.snapshot))} | <span class="badge ${severityClass(item.tier)}">${escapeHtml(item.tier)} ${escapeHtml(item.score)}</span></div>
    <div class="muted-line">timestamp: ${escapeHtml(item.timestamp || '-')}</div>
    <div class="muted-line">drivers: ${escapeHtml(JSON.stringify(drivers))}</div>
    <ul>${alertHtml}</ul>
  `;
}

function fmtSnapshotLabel(name) {
  const m = String(name || '').match(/snapshot-(\d{8})T(\d{4})\.json/);
  if (!m) return name;
  const d = m[1];
  const t = m[2];
  return `${d.slice(4, 6)}/${d.slice(6, 8)} ${t.slice(0, 2)}:${t.slice(2, 4)}`;
}

function ensureLineChart(key, label, color) {
  if (!chartCanvases[key]) return null;
  if (typeof Chart === 'undefined') return null;
  if (chartInstances[key]) return chartInstances[key];
  chartInstances[key] = new Chart(chartCanvases[key], {
    type: 'line',
    data: { labels: [], datasets: [{
      label,
      data: [],
      borderColor: color,
      backgroundColor: color.replace('1)', '0.18)'),
      borderWidth: 2,
      tension: 0.25,
      pointRadius: 0,
      fill: true,
    }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#95a3c4', maxTicksLimit: 8 }, grid: { color: 'rgba(72,151,255,0.06)' } },
        y: { ticks: { color: '#95a3c4' }, grid: { color: 'rgba(72,151,255,0.08)' }, beginAtZero: true },
      },
    },
  });
  return chartInstances[key];
}

function ensureMultiLineChart(key, datasets) {
  if (!chartCanvases[key]) return null;
  if (typeof Chart === 'undefined') return null;
  if (chartInstances[key]) return chartInstances[key];
  chartInstances[key] = new Chart(chartCanvases[key], {
    type: 'line',
    data: { labels: [], datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { labels: { color: '#cfe4ff', boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: '#95a3c4', maxTicksLimit: 8 }, grid: { color: 'rgba(72,151,255,0.06)' } },
        y: { ticks: { color: '#95a3c4' }, grid: { color: 'rgba(72,151,255,0.08)' }, beginAtZero: true },
      },
    },
  });
  return chartInstances[key];
}

async function loadReplayCharts() {
  if (typeof Chart === 'undefined') {
    chartsStatus.textContent = 'Chart.js indisponivel (offline?). Charts desativados.';
    return;
  }
  try {
    const res = await fetch('/api/replay/timeseries?limit=180');
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    const items = data.items || [];
    if (!items.length) {
      chartsStatus.textContent = 'Sem snapshots persistidos ainda.';
      return;
    }
    const labels = items.map((it) => fmtSnapshotLabel(it.snapshot));
    const signalsData = items.map((it) => it.signals_total || 0);
    const tradesData = items.map((it) => it.trades_total || 0);
    const alertsData = items.map((it) => it.alerts_count || 0);
    const severityData = items.map((it) => it.severity_score || 0);

    const signalsChart = ensureLineChart('signals', 'Signals', 'rgba(69, 208, 255, 1)');
    const tradesChart = ensureLineChart('trades', 'Trades', 'rgba(73, 209, 122, 1)');
    const alertsChart = ensureMultiLineChart('alerts', [
      {
        label: 'Alerts',
        data: [],
        borderColor: 'rgba(255, 143, 87, 1)',
        backgroundColor: 'rgba(255, 143, 87, 0.18)',
        borderWidth: 2,
        tension: 0.25,
        pointRadius: 0,
        fill: true,
        yAxisID: 'y',
      },
      {
        label: 'Severity score',
        data: [],
        borderColor: 'rgba(255, 110, 110, 1)',
        backgroundColor: 'rgba(255, 110, 110, 0.12)',
        borderWidth: 2,
        tension: 0.25,
        pointRadius: 0,
        fill: false,
        borderDash: [5, 4],
        yAxisID: 'y',
      },
    ]);

    if (signalsChart) {
      signalsChart.data.labels = labels;
      signalsChart.data.datasets[0].data = signalsData;
      signalsChart.update();
    }
    if (tradesChart) {
      tradesChart.data.labels = labels;
      tradesChart.data.datasets[0].data = tradesData;
      tradesChart.update();
    }
    if (alertsChart) {
      alertsChart.data.labels = labels;
      alertsChart.data.datasets[0].data = alertsData;
      alertsChart.data.datasets[1].data = severityData;
      alertsChart.update();
    }

    const last = items[items.length - 1];
    chartsStatus.textContent = `${items.length} pontos | ultimo: ${fmtSnapshotLabel(last.snapshot)} | severidade ${last.severity_tier}`;
  } catch (err) {
    // textContent is auto-escaped, no escapeHtml needed.
    chartsStatus.textContent = 'Falha ao carregar charts: ' + (err && err.message ? err.message : err);
  }
}

async function loadIncidentQueue() {
  try {
    const tier = (queueSeverityFilter?.value || '').trim().toUpperCase();
    const q = (queueSearch?.value || '').trim();
    const query = new URLSearchParams({ limit: String(queuePageSize), offset: String(queueOffset) });
    if (tier) query.set('tier', tier);
    if (q) query.set('q', q);
    const res = await fetch(`/api/incidents/queue?${query.toString()}`);
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    const items = data.items || [];
    const total = Number(data.count || 0);
    const currentPage = Math.floor(queueOffset / queuePageSize) + 1;
    const totalPages = Math.max(1, Math.ceil(total / queuePageSize));
    if (queuePageStatus) queuePageStatus.textContent = `Page ${currentPage}/${totalPages} • ${total} incidents`;
    if (queuePrevBtn) queuePrevBtn.disabled = queueOffset <= 0;
    if (queueNextBtn) queueNextBtn.disabled = !Boolean(data.has_more);
    if (!items.length) {
      incidentQueueRoot.innerHTML = '<div class="muted-line">Sem incidentes ativos.</div>';
      renderIncidentDetail(null);
      return;
    }
    incidentQueueRoot.innerHTML = items.map((it, idx) => {
      const drivers = it.drivers || {};
      const driverChips = [
        drivers.kill_switch ? `<span class="driver kill">kill x${escapeHtml(drivers.kill_switch)}</span>` : '',
        drivers.critical_alerts ? `<span class="driver crit">crit x${escapeHtml(drivers.critical_alerts)}</span>` : '',
        drivers.warning_alerts ? `<span class="driver warn">warn x${escapeHtml(drivers.warning_alerts)}</span>` : '',
        drivers.anomaly_pause ? `<span class="driver anom">pause x${escapeHtml(drivers.anomaly_pause)}</span>` : '',
        drivers.breached_limits ? `<span class="driver breach">breach x${escapeHtml(drivers.breached_limits)}</span>` : '',
        drivers.sla_degraded ? `<span class="driver sla">sla x${escapeHtml(drivers.sla_degraded)}</span>` : '',
      ].filter(Boolean).join(' ');
      const sevClass = severityClass(it.tier);
      const safeSnapshot = escapeHtml(it.snapshot);
      return `
        <div class="incident-row ${sevClass}" data-snapshot="${safeSnapshot}">
          <div class="incident-head">
            <span class="rank">#${idx + 1}</span>
            <span class="badge ${sevClass}">${escapeHtml(it.tier)} ${escapeHtml(it.score)}</span>
            <strong>${escapeHtml(fmtSnapshotLabel(it.snapshot))}</strong>
            <span class="muted-line">${safeSnapshot}</span>
            <div class="incident-actions">
              <button type="button" data-snapshot="${safeSnapshot}" class="open-incident-replay">Replay</button>
              <button type="button" data-snapshot="${safeSnapshot}" class="compare-incident-baseline">Open Compare with Baseline</button>
              <button type="button" data-snapshot="${safeSnapshot}" class="open-incident-drawer">Incident Drawer</button>
            </div>
          </div>
          <div class="incident-drivers">${driverChips || '<span class="muted-line">sem drivers</span>'}</div>
        </div>`;
    }).join('');
    incidentQueueRoot.querySelectorAll('.open-incident-replay').forEach((btn) => {
      btn.addEventListener('click', () => {
        const name = btn.dataset.snapshot;
        const idx = replaySnapshots.indexOf(name);
        if (idx >= 0) loadReplayByIndex(idx);
      });
    });
    incidentQueueRoot.querySelectorAll('.compare-incident-baseline').forEach((btn) => {
      btn.addEventListener('click', () => {
        const snapshot = btn.dataset.snapshot || '';
        compareWithBaseline(snapshot);
      });
    });
    incidentQueueRoot.querySelectorAll('.open-incident-drawer').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const snapshot = btn.dataset.snapshot || '';
        await openIncidentDrawer(snapshot);
      });
    });
    incidentQueueRoot.querySelectorAll('.incident-row').forEach((row) => {
      row.addEventListener('click', () => {
        const snapshot = row.getAttribute('data-snapshot');
        const found = items.find((it) => it.snapshot === snapshot);
        renderIncidentDetail(found || null);
      });
    });
    renderIncidentDetail(items[0]);
  } catch (err) {
    incidentQueueRoot.innerHTML = `<div class="muted-line">Falha ao carregar fila: ${escapeHtml(err.message)}</div>`;
    renderIncidentDetail(null);
  }
}

async function openIncidentDrawer(snapshot) {
  if (!snapshot || !riskModal || !riskModalBody || !riskModalTitle) return;
  riskModalTitle.textContent = `Incident Drawer • ${fmtSnapshotLabel(snapshot)}`;
  riskModalBody.innerHTML = '<div class="muted-line">Carregando detalhes do incidente...</div>';
  riskModal.classList.remove('hidden');
  try {
    const res = await fetch(`/api/incidents/detail?snapshot=${encodeURIComponent(snapshot)}`);
    if (!res.ok) throw new Error(`http ${res.status}`);
    const d = await res.json();
    const sev = d.severity || {};
    const ov = d.overview || {};
    const cmp = d.compare || {};
    const delta = cmp.overview_delta || {};
    const alerts = (d.alerts || []).map((a) => `<li><strong>${escapeHtml(a.code || 'ALERT')}</strong> — ${escapeHtml(a.message || '-')}</li>`).join('') || '<li>Sem alertas.</li>';
    const riskRows = (cmp.risk_delta || []).map((r) => `<tr><td>${escapeHtml(r.symbol)}</td><td>${escapeHtml(r.approved)}</td><td>${escapeHtml(r.reduced)}</td><td>${escapeHtml(r.rejected)}</td><td>${escapeHtml(r.kill_switch)}</td></tr>`).join('') || '<tr><td colspan="5">Sem delta de risco.</td></tr>';
    const slaRows = (cmp.sla_delta || []).map((r) => `<tr><td>${escapeHtml(r.hero)}</td><td>${escapeHtml(r.avg_seconds_delta)}</td><td>${escapeHtml(r.samples_delta)}</td></tr>`).join('') || '<tr><td colspan="3">Sem delta de SLA.</td></tr>';
    riskModalBody.innerHTML = `
      <div><span class="badge ${severityClass(sev.tier)}">${escapeHtml(sev.tier || 'NONE')} ${escapeHtml(sev.score ?? 0)}</span> <span class="muted-line">snapshot: ${escapeHtml(d.snapshot)}</span></div>
      <div class="muted-line">baseline: ${escapeHtml(d.baseline_snapshot || 'N/A')}</div>
      <div class="muted-line">overview atual: signals=${escapeHtml(ov.total_signals ?? '-')} trades=${escapeHtml(ov.total_trades ?? '-')} trades_today=${escapeHtml(ov.trades_today ?? '-')} exec_today=${escapeHtml(ov.executions_today ?? '-')}</div>
      <div class="muted-line">overview delta: signals=${escapeHtml(delta.total_signals ?? '-')} trades=${escapeHtml(delta.total_trades ?? '-')} trades_today=${escapeHtml(delta.trades_today ?? '-')} exec_today=${escapeHtml(delta.executions_today ?? '-')}</div>
      <h4>Alerts</h4>
      <ul>${alerts}</ul>
      <h4>Risk Delta</h4>
      <table class="compare-table"><thead><tr><th>Symbol</th><th>ΔApproved</th><th>ΔReduced</th><th>ΔRejected</th><th>ΔKill</th></tr></thead><tbody>${riskRows}</tbody></table>
      <h4>Hero SLA Delta</h4>
      <table class="compare-table"><thead><tr><th>Hero</th><th>ΔAvg(s)</th><th>ΔSamples</th></tr></thead><tbody>${slaRows}</tbody></table>
    `;
  } catch (err) {
    riskModalBody.innerHTML = `<div class="muted-line">Falha ao carregar Incident Drawer: ${escapeHtml(err.message)}</div>`;
  }
}

async function compareWithBaseline(snapshot) {
  if (!snapshot) return;
  if (!replaySnapshots.length) await loadReplaySnapshots();
  const idx = replaySnapshots.indexOf(snapshot);
  if (idx < 0) {
    compareOutput.textContent = `Snapshot nao encontrado para comparar: ${snapshot}`;
    return;
  }
  const baseline = replaySnapshots[idx + 1];
  if (!baseline) {
    compareOutput.textContent = `Sem baseline anterior para ${snapshot}.`;
    return;
  }
  compareA.value = snapshot;
  compareB.value = baseline;
  await runCompare();
  compareOutput.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function exportIncidentsCsv() {
  const tier = (queueSeverityFilter?.value || '').trim().toUpperCase();
  const q = (queueSearch?.value || '').trim();
  let url = '/api/incidents/export?limit=2000&scan=3000';
  if (tier) url += `&tier=${encodeURIComponent(tier)}`;
  if (q) url += `&q=${encodeURIComponent(q)}`;
  window.open(url, '_blank');
}

async function loadIncidentLatest() {
  const res = await fetch('/api/replay/incident/latest');
  if (!res.ok) {
    compareOutput.textContent = 'Nenhum incident bundle de kill switch encontrado.';
    return;
  }
  const d = await res.json();
  const alerts = (d.alerts || []).map((a) => `<div>${escapeHtml(a.code)}: ${escapeHtml(a.message)}</div>`).join('');
  const sev = d.severity || {};
  const sevClass = severityClass(sev.tier);
  compareOutput.innerHTML = `
    <div><strong>Incident Bundle</strong> <span class="badge ${sevClass}">${escapeHtml(sev.tier || 'NONE')} ${escapeHtml(sev.score ?? 0)}</span></div>
    <div>Snapshot incidente: ${escapeHtml(d.incident_snapshot)}</div>
    <div>Snapshot baseline: ${escapeHtml(d.baseline_snapshot ?? 'N/A')}</div>
    <div>${alerts}</div>
    <div>Overview: signals=${escapeHtml(d.overview?.total_signals ?? '-')} trades=${escapeHtml(d.overview?.total_trades ?? '-')}</div>
  `;
}

applyPrefs();
connect();
enhanceTitlesWithHelp();
renderAgentsRoster();
bindFilterEvents();
bindSidebarScrollSpy();
loadReplaySnapshots();
loadIncidentBundles();
refreshApiHealth();
setInterval(refreshApiHealth, 30000);
riskModalClose.addEventListener('click', closeRiskDrilldown);
riskModal.addEventListener('click', (e) => {
  if (e.target === riskModal) closeRiskDrilldown();
});
replayLiveBtn.addEventListener('click', setLiveMode);
replayPrevBtn.addEventListener('click', () => {
  if (replayMode === 'live') return;
  loadReplayByIndex(Math.max(0, replayIndex - 1));
});
replayNextBtn.addEventListener('click', () => {
  if (replayMode === 'live') return;
  loadReplayByIndex(Math.min(replaySnapshots.length - 1, replayIndex + 1));
});
replayPlayBtn.addEventListener('click', toggleReplayPlay);
replaySnapshotSelect.addEventListener('change', (e) => {
  const idx = Number(e.target.value);
  if (!Number.isFinite(idx)) return;
  loadReplayByIndex(idx);
});
replayExportJsonBtn.addEventListener('click', () => exportReplay('json'));
replayExportCsvBtn.addEventListener('click', () => exportReplay('csv'));
compareRunBtn.addEventListener('click', runCompare);
incidentLatestBtn.addEventListener('click', loadIncidentLatest);
if (prefsResetBtn) prefsResetBtn.addEventListener('click', resetPrefs);
if (langToggle) langToggle.addEventListener('change', () => {
  const next = (langToggle.value === 'en') ? 'en' : 'pt';
  applyLanguage(next);
  savePrefs({ lang: next });
});
if (themeToggleBtn) themeToggleBtn.addEventListener('click', () => {
  const current = document.body.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  const next = current === 'light' ? 'dark' : 'light';
  applyTheme(next);
  savePrefs({ theme: next });
  applyLanguage(currentLang);
});
if (incidentDownloadBtn) incidentDownloadBtn.addEventListener('click', downloadIncidentBundle);
if (incidentDownloadSelectedBtn) {
  incidentDownloadSelectedBtn.addEventListener('click', downloadSelectedIncidentBundle);
}
if (chartsRefreshBtn) chartsRefreshBtn.addEventListener('click', loadReplayCharts);
if (queueRefreshBtn) queueRefreshBtn.addEventListener('click', loadIncidentQueue);
if (queueSeverityFilter) queueSeverityFilter.addEventListener('change', () => {
  queueOffset = 0;
  loadIncidentQueue();
});
if (queueSeverityFilter) queueSeverityFilter.addEventListener('change', () => {
  savePrefs({ queueSeverity: queueSeverityFilter.value || '' });
});
if (queueSearch) queueSearch.addEventListener('input', () => {
  if (queueSearchDebounce) clearTimeout(queueSearchDebounce);
  queueSearchDebounce = setTimeout(() => {
    queueOffset = 0;
    loadIncidentQueue();
    savePrefs({ queueSearch: queueSearch.value || '' });
  }, 220);
});
if (queuePrevBtn) queuePrevBtn.addEventListener('click', () => {
  queueOffset = Math.max(0, queueOffset - queuePageSize);
  loadIncidentQueue();
});
if (queueNextBtn) queueNextBtn.addEventListener('click', () => {
  queueOffset += queuePageSize;
  loadIncidentQueue();
});
if (incidentExportCsvBtn) incidentExportCsvBtn.addEventListener('click', exportIncidentsCsv);
if (marketRefreshBtn) marketRefreshBtn.addEventListener('click', async () => {
  await loadMarketCandles();
  await loadMarketDepth();
  await loadMarketTrades();
  await loadMarketDiagnostics();
  await loadMarketStatus();
});
if (marketLiveToggleBtn) marketLiveToggleBtn.addEventListener('click', () => {
  if (marketLivePaused) {
    marketLivePaused = false;
    savePrefs({ marketLivePaused: false });
    marketLiveToggleBtn.textContent = t('market_pause');
    bootMarket();
  } else {
    marketLivePaused = true;
    savePrefs({ marketLivePaused: true });
    marketLiveToggleBtn.textContent = t('market_resume');
    marketAutoRefreshTimer = _clearTimer(marketAutoRefreshTimer);
    if (marketTickerReconnectTimer) {
      clearTimeout(marketTickerReconnectTimer);
      marketTickerReconnectTimer = null;
    }
    if (marketTickerWs) {
      marketTickerWs.onclose = null;
      marketTickerWs.close();
      marketTickerWs = null;
    }
    if (marketStatus) {
      marketStatus.textContent = `${marketSymbol?.value || 'MARKET'} ${marketTimeframe?.value || ''} • live paused`;
    }
  }
});
if (marketSymbol) marketSymbol.addEventListener('change', async () => {
  savePrefs({ marketSymbol: marketSymbol.value || '' });
  marketFirstRender = true;
  syncTradingViewSymbolAndInterval();
  await loadMarketCandles();
  await loadMarketDepth();
  await loadMarketTrades();
  connectMarketTickerWs();
});
if (marketTimeframe) marketTimeframe.addEventListener('change', async () => {
  savePrefs({ marketTimeframe: marketTimeframe.value || '' });
  marketFirstRender = true;
  syncTradingViewSymbolAndInterval();
  await loadMarketCandles();
});
if (marketRefreshInterval) marketRefreshInterval.addEventListener('change', () => {
  const parsed = Number(marketRefreshInterval.value || 3000);
  marketRefreshMs = Number.isFinite(parsed) && parsed >= 1000 ? parsed : 3000;
  savePrefs({ marketRefreshMs });
  if (!marketLivePaused) bootMarket();
});

// Auto-refresh helpers. We re-arm the timers on visibility change so the
// dashboard doesn't burn CPU/network/battery polling while the user is on
// another tab — and immediately fetches fresh data when they come back.
function _clearTimer(t) { if (t) clearInterval(t); return null; }

function bootCharts() {
  loadReplayCharts();
  chartsAutoRefreshTimer = _clearTimer(chartsAutoRefreshTimer);
  if (!document.hidden) {
    chartsAutoRefreshTimer = setInterval(loadReplayCharts, 30000);
  }
}
function bootQueue() {
  loadIncidentQueue();
  queueAutoRefreshTimer = _clearTimer(queueAutoRefreshTimer);
  if (!document.hidden) {
    queueAutoRefreshTimer = setInterval(loadIncidentQueue, 30000);
  }
}
function bootMarket() {
  if (marketLivePaused) return;
  loadMarketCandles();
  loadMarketDepth();
  loadMarketTrades();
  loadMarketDiagnostics();
  loadMarketStatus();
  connectMarketTickerWs();
  marketAutoRefreshTimer = _clearTimer(marketAutoRefreshTimer);
  if (!document.hidden) {
    marketAutoRefreshTimer = setInterval(() => {
      loadMarketCandles();
      loadMarketDepth();
      loadMarketTrades();
      loadMarketDiagnostics();
      loadMarketStatus();
    }, marketRefreshMs);
  }
}
function bootPnl() {
  loadPnl();
  pnlAutoRefreshTimer = _clearTimer(pnlAutoRefreshTimer);
  // PnL changes slowly (1× per day at most) — 60s refresh is plenty and
  // saves DB cycles compared to charts/queue (30s).
  if (!document.hidden) {
    pnlAutoRefreshTimer = setInterval(loadPnl, 60000);
  }
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    chartsAutoRefreshTimer = _clearTimer(chartsAutoRefreshTimer);
    queueAutoRefreshTimer = _clearTimer(queueAutoRefreshTimer);
    marketAutoRefreshTimer = _clearTimer(marketAutoRefreshTimer);
    pnlAutoRefreshTimer = _clearTimer(pnlAutoRefreshTimer);
    killswitchAutoRefreshTimer = _clearTimer(killswitchAutoRefreshTimer);
    positionsAutoRefreshTimer = _clearTimer(positionsAutoRefreshTimer);
    internalsAutoRefreshTimer = _clearTimer(internalsAutoRefreshTimer);
    tradesTimelineAutoRefreshTimer = _clearTimer(tradesTimelineAutoRefreshTimer);
  } else {
    bootCharts();
    bootQueue();
    bootMarket();
    bootPnl();
    bootKillswitch();
    bootPositions();
    bootInternals();
    bootTradesTimeline();
    bootFunding();
  }
});

if (positionsRefreshBtn) positionsRefreshBtn.addEventListener('click', loadPositions);
if (internalsRefreshBtn) internalsRefreshBtn.addEventListener('click', loadInternals);
if (tradesTimelineRefresh) tradesTimelineRefresh.addEventListener('click', loadTradesTimeline);
if (tradesTimelineHours) tradesTimelineHours.addEventListener('change', () => {
  savePrefs({ tradesTimelineHours: tradesTimelineHours.value || '24' });
  loadTradesTimeline();
});
if (filterMode) {
  filterMode.addEventListener('change', () => {
    savePrefs({ filterMode: filterMode.value || 'contains' });
    if (lastPayload) applyFilters(lastPayload);
  });
}

// Kill switch wiring.
if (killswitchEngageBtn) killswitchEngageBtn.addEventListener('click', () => openKillswitchModal('engage'));
if (killswitchReleaseBtn) killswitchReleaseBtn.addEventListener('click', () => openKillswitchModal('release'));
if (killswitchModalSubmit) killswitchModalSubmit.addEventListener('click', submitKillswitchAction);
if (killswitchModalCancel) killswitchModalCancel.addEventListener('click', closeKillswitchModal);
if (killswitchModalClose) killswitchModalClose.addEventListener('click', closeKillswitchModal);
if (authButton) authButton.addEventListener('click', () => {
  if (_authState.authenticated) return logoutAuth();
  openAuthModal();
});
if (authModalClose) authModalClose.addEventListener('click', closeAuthModal);
if (authCancelBtn) authCancelBtn.addEventListener('click', closeAuthModal);
if (authSubmitBtn) authSubmitBtn.addEventListener('click', submitAuthLogin);
if (authPassword) authPassword.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); submitAuthLogin(); }
});
if (authModal) authModal.addEventListener('click', (e) => {
  if (e.target === authModal) closeAuthModal();
});
refreshAuthState();
setInterval(refreshAuthState, 60000);
if (killswitchModal) killswitchModal.addEventListener('click', (e) => {
  if (e.target === killswitchModal) closeKillswitchModal();
});

// PnL toolbar wiring.
if (pnlRefreshBtn) pnlRefreshBtn.addEventListener('click', loadPnl);
if (pnlWindowSelect) {
  pnlWindowSelect.addEventListener('change', () => {
    savePrefs({ pnlWindow: pnlWindowSelect.value || '30' });
    loadPnl();
  });
}

// ============================================================
// Story 040 — Dashboard v2
// Page Navigation · Financial TopBar · Widget Customizer · TradeNow
// ============================================================

// ── Page→section mapping ─────────────────────────────────────
const _PAGE_SECTIONS = {
  overview:    ['sec-office', 'sec-live-market', 'sec-metrics'],
  wallet:      ['sec-killswitch', 'sec-pnl', 'sec-positions', 'sec-funding'],
  performance: ['sec-trades-timeline', 'sec-replay-charts', 'sec-hero-sla'],
  agents:      ['sec-layers', 'sec-agents', 'sec-internals'],
  trades:      ['sec-signals', 'sec-trades'],
  risk:        ['sec-risk', 'sec-anomalies', 'sec-incident-queue'],
  logs:        ['sec-audit', 'sec-replay-player', 'sec-manual', 'sec-timeline', 'sec-symbol-timeline'],
  settings:    ['sec-trading-settings', 'sec-settings', 'sec-filters'],
  live:        ['sec-live-trading'],
};
const _ALL_PAGE_SECTIONS = Object.values(_PAGE_SECTIONS).flat();

/** Switch to a page, show only its sections, then apply widget prefs. */
function _mkSetPage(pageKey) {
  if (!_PAGE_SECTIONS[pageKey]) return;

  // Update nav button active state
  document.querySelectorAll('.page-nav-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.page === pageKey);
  });

  // Hide ALL known sections first
  _ALL_PAGE_SECTIONS.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.add('page-section-hidden');
  });

  // Show only the sections belonging to this page
  (_PAGE_SECTIONS[pageKey] || []).forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('page-section-hidden');
  });

  // Apply per-widget visibility prefs on top
  _mkApplyWidgetPrefs(pageKey);

  // Persist choice
  try { localStorage.setItem('mekka_current_page', pageKey); } catch (_) {}

  // Render widget customizer if landing on settings
  if (pageKey === 'settings') _mkRenderWidgetCustomizer();

  // Boot live chart on first visit to "live" page
  if (pageKey === 'live') _ensureLiveChartBooted();
}

/** Boot page nav: wire buttons (single registration), restore last page. */
function _mkBootPageNav() {
  document.querySelectorAll('.page-nav-btn').forEach(btn => {
    btn.addEventListener('click', () => _mkSetPage(btn.dataset.page));
  });
  let saved = 'overview';
  try { saved = localStorage.getItem('mekka_current_page') || 'overview'; } catch (_) {}
  if (!_PAGE_SECTIONS[saved]) saved = 'overview';
  _mkSetPage(saved);
}

// ── Financial TopBar ─────────────────────────────────────────
let _ftbTimer = null;
let _ftbLastUpdate = null;

/** Refresh the financial topbar cards. */
async function _mkLoadTopBar() {
  const set = (id, val, cls) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = val;
    if (cls) el.className = `ftb-value ${cls}`;
    else el.className = 'ftb-value';
  };

  try {
    // Wallet + day PnL
    const pnlRes = await fetch('/api/pnl/summary?window=1').then(r => r.json()).catch(() => null);
    if (pnlRes && pnlRes.window) {
      const eq = pnlRes.window.latest_equity_usd;
      const pnl = pnlRes.window.pnl_usd;
      const startEq = eq - (pnl || 0);
      const pnlPct = startEq > 0 ? (pnl / startEq * 100) : null;

      set('ftb-wallet-val', eq != null ? fmtMoney(eq) : '—');
      const pnlCls = pnl > 0 ? 'positive' : pnl < 0 ? 'negative' : '';
      set('ftb-daypnl-val', pnl != null ? `${pnl >= 0 ? '+' : ''}${fmtMoney(pnl)}` : '—', pnlCls);
      set('ftb-daypnl-pct-val',
        pnlPct != null ? `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%` : '—',
        pnlCls
      );
    }
  } catch (_) {}

  try {
    // Open positions
    const posRes = await fetch('/api/positions').then(r => r.json()).catch(() => null);
    if (posRes) {
      const count = posRes.count ?? (Array.isArray(posRes.items) ? posRes.items.length : (posRes.open_positions_count ?? '—'));
      set('ftb-positions-val', String(count));
    }
  } catch (_) {}

  try {
    // Risk level + agent status from overview
    const ovRes = await fetch('/api/overview').then(r => r.json()).catch(() => null);
    if (ovRes) {
      const dd = ovRes.drawdown_pct != null ? (ovRes.drawdown_pct * 100).toFixed(1) + '%' : '—';
      const ks = ovRes.kill_switch_active;
      const riskLabel = ks ? '🔴 KS' : dd;
      const riskCls = ks ? 'negative' : '';
      set('ftb-risk-val', riskLabel, riskCls);

      // Agent status: count breakers
      const breakers = ovRes.breakers || {};
      const totalBreakers = Object.keys(breakers).length;
      const activeBreakers = Object.values(breakers).filter(v => v).length;
      const agentLabel = activeBreakers > 0
        ? `⚠️ ${activeBreakers}/${totalBreakers}`
        : `🟢 ${totalBreakers > 0 ? 'OK' : 'standby'}`;
      set('ftb-agents-val', agentLabel, activeBreakers > 0 ? 'negative' : '');
    }
  } catch (_) {}

  // Last update timestamp
  _ftbLastUpdate = new Date();
  const upEl = document.getElementById('ftb-update-val');
  if (upEl) upEl.textContent = _ftbLastUpdate.toLocaleTimeString('pt-BR', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
}

function _mkBootTopBar() {
  _mkLoadTopBar();
  if (_ftbTimer) clearInterval(_ftbTimer);
  _ftbTimer = setInterval(_mkLoadTopBar, 30000);
}

// ── Widget Customizer ────────────────────────────────────────
const _WIDGET_LABELS = {
  'sec-office':         '⬡ Pixel 3D Office',
  'sec-live-market':    '📈 Market Live',
  'sec-metrics':        '🎯 Mission Metrics',
  'sec-killswitch':     '🔴 Kill Switch',
  'sec-pnl':            '💰 Equity & PnL',
  'sec-positions':      '📋 Open Positions',
  'sec-funding':        '📊 Funding Rates',
  'sec-trades-timeline':'⏱ Trades Timeline',
  'sec-replay-charts':  '🔁 Replay Charts',
  'sec-hero-sla':       '🦸 Hero SLA',
  'sec-layers':         '🗺 Layer Command Map',
  'sec-agents':         '🤖 Agents Roster',
  'sec-internals':      '⚙️ Dashboard Internals',
  'sec-signals':        '🔮 Vision Signals',
  'sec-trades':         '⚡ Iron Man Executions',
  'sec-risk':           '🛡 Risk Heatmap',
  'sec-anomalies':      '🚨 Anomaly Console',
  'sec-incident-queue': '📥 Incident Queue',
  'sec-audit':          '📝 Audit Stream',
  'sec-replay-player':  '▶️ Replay Player',
  'sec-manual':         '📖 Mini Manual',
  'sec-filters':           '🔍 Filters',
  'sec-trading-settings':  '⚡ Modos de Trading',
};
const _WIDGET_PREFS_KEY = 'mekka_widget_prefs_v1';

/** Load widget prefs from localStorage. */
function _mkLoadWidgetPrefs() {
  try {
    const raw = localStorage.getItem(_WIDGET_PREFS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (_) { return {}; }
}

/** Save widget prefs to localStorage AND sync to server (Story 042). */
function _mkSaveWidgetPrefs(prefs) {
  try { localStorage.setItem(_WIDGET_PREFS_KEY, JSON.stringify(prefs)); } catch (_) {}
  window._mkWidgetPrefs = prefs;
  // Async server-side persistence — fire-and-forget (no await needed)
  fetch('/api/prefs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prefs }),
  }).catch(() => {}); // silent on network error
}

/**
 * Pull server-side prefs and merge with localStorage.
 * Server wins on conflict (last save persists across restarts).
 * Called once at boot from _mkBootDashboardV2.
 */
async function _mkSyncPrefsFromServer() {
  try {
    const res = await fetch('/api/prefs');
    if (!res.ok) return;
    const { prefs: serverPrefs } = await res.json();
    if (!serverPrefs || typeof serverPrefs !== 'object') return;
    // Merge: server prefs take priority over stale localStorage
    const local = _mkLoadWidgetPrefs();
    const merged = { ...local, ...serverPrefs };
    try { localStorage.setItem(_WIDGET_PREFS_KEY, JSON.stringify(merged)); } catch (_) {}
    window._mkWidgetPrefs = merged;
  } catch (_) {}
}

/** Apply widget prefs: hide/show sections on the current page. */
function _mkApplyWidgetPrefs(activePage) {
  const prefs = _mkLoadWidgetPrefs();
  const pageSections = _PAGE_SECTIONS[activePage] || [];
  pageSections.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const visible = prefs[id] !== false; // default: visible
    el.classList.toggle('page-section-hidden', !visible);
  });
}

/** Render widget customizer checkboxes in #widget-customizer. */
function _mkRenderWidgetCustomizer() {
  const container = document.getElementById('widget-customizer');
  if (!container) return;
  const prefs = _mkLoadWidgetPrefs();
  container.innerHTML = '';

  Object.entries(_WIDGET_LABELS).forEach(([id, label]) => {
    const checked = prefs[id] !== false;
    const item = document.createElement('div');
    item.className = `widget-item${!checked ? ' hidden-widget' : ''}`;
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.id = `widget-cb-${id}`;
    cb.checked = checked;
    const lbl = document.createElement('label');
    lbl.htmlFor = `widget-cb-${id}`;
    lbl.textContent = label;
    item.appendChild(cb);
    item.appendChild(lbl);
    cb.addEventListener('change', () => {
      const p = _mkLoadWidgetPrefs();
      p[id] = cb.checked;
      _mkSaveWidgetPrefs(p);
      item.classList.toggle('hidden-widget', !cb.checked);
      // Apply immediately if the section is currently visible
      const el = document.getElementById(id);
      if (el && !el.classList.contains('page-section-hidden')) {
        el.classList.toggle('page-section-hidden', !cb.checked);
      }
    });
    container.appendChild(item);
  });
}

// ── TradeNow state ────────────────────────────────────────────
// DOM refs are resolved lazily inside _mkBootTradeNow to guarantee the
// elements exist regardless of when the script is parsed.
let _tradeModal       = null;
let _tradeModalClose  = null;
let _tradeGuardrails  = null;
let _tradeRecCard     = null;
let _tradeConfirmBtn  = null;
let _tradeCancelBtn   = null;
let _tradeResultClose = null;
let _tradeNowBtn      = null;

let _currentRecId = null;
let _currentRec   = null;

function _tradeShowPanel(panelId) {
  ['trade-modal-loading', 'trade-modal-recommendation', 'trade-modal-result'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('hidden', el.id !== panelId);
  });
}

function _tradeOpenModal() {
  if (_tradeModal) {
    _tradeModal.classList.remove('hidden');
    _tradeShowPanel('trade-modal-loading');
  }
}

function _tradeCloseModal() {
  if (_tradeModal) _tradeModal.classList.add('hidden');
  _currentRecId = null;
  _currentRec   = null;
  if (_tradeNowBtn) _tradeNowBtn.disabled = false;
}

/** Client-side pre-flight: check obvious blockers before calling API. */
function _tradeClientGuardrails() {
  const walletVal = document.getElementById('ftb-wallet-val');
  const walletText = walletVal ? walletVal.textContent : '';
  // If wallet shows $0.00 or — it's a problem
  if (!walletText || walletText === '—' || walletText === '$0.00') {
    return { ok: false, reason: 'Carteira indisponível — atualize os dados antes de operar.' };
  }
  // If kill switch indicator shows KS active in risk card
  const riskEl = document.getElementById('ftb-risk-val');
  if (riskEl && riskEl.textContent.includes('KS')) {
    return { ok: false, reason: 'Kill switch ativo — libere antes de executar ordens.' };
  }
  // Data staleness check
  if (_ftbLastUpdate) {
    const ageMs = Date.now() - _ftbLastUpdate.getTime();
    if (ageMs > 5 * 60 * 1000) {
      return { ok: false, reason: 'Dados desatualizados (>5 min) — aguarde próxima atualização.' };
    }
  }
  return { ok: true, reason: '' };
}

function _tradeRenderGuardrails(checks) {
  if (!_tradeGuardrails) return;
  _tradeGuardrails.innerHTML = checks.map(c => `
    <span class="guardrail-chip ${c.ok ? 'ok' : 'fail'}" title="${escapeHtml(c.detail)}">
      ${c.ok ? '✅' : '❌'} ${escapeHtml(c.name.replace(/_/g, ' '))}
    </span>
  `).join('');
}

function _tradeRenderRecommendation(rec, isPaper) {
  if (!_tradeRecCard) return;
  if (!rec) {
    _tradeRecCard.innerHTML = '<p class="muted-line">Nenhuma recomendação disponível.</p>';
    if (_tradeConfirmBtn) _tradeConfirmBtn.disabled = true;
    return;
  }
  const dir = rec.direction || '—';
  const dirCls = dir === 'LONG' ? 'long' : 'short';
  const confPct = rec.confidence != null ? (rec.confidence * 100).toFixed(1) + '%' : '—';
  const entry = rec.entry_price ? fmtMoney(rec.entry_price) : '—';
  const sl = rec.stop_loss ? fmtMoney(rec.stop_loss) : '—';
  const tp = rec.take_profit ? fmtMoney(rec.take_profit) : '—';
  const size = rec.size_pct != null ? (rec.size_pct * 100).toFixed(2) + '%' : '—';
  const risk = rec.risk_usd != null ? fmtMoney(rec.risk_usd) : '—';
  const sourceBadge = rec.source === 'mock'
    ? '<span style="color:#f7a11a;font-size:0.78rem;">⚠️ MOCK — sem sinal real recente</span>'
    : `<span style="color:#26d07c;font-size:0.78rem;">✅ Agentes</span>`;
  const paperBadge = isPaper
    ? '<span style="color:#888;font-size:0.78rem;"> (PAPER MODE)</span>'
    : '<span style="color:#e94560;font-size:0.78rem;"> ⚠️ LIVE MODE</span>';

  _tradeRecCard.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <strong style="font-size:1.1rem;">${escapeHtml(rec.symbol || '—')}</strong>
      <div>${sourceBadge}${paperBadge}</div>
    </div>
    <div class="trade-rec-row">
      <span class="trade-rec-label">Direção</span>
      <span class="trade-rec-value ${dirCls}">${dir}</span>
    </div>
    <div class="trade-rec-row">
      <span class="trade-rec-label">Entrada estimada</span>
      <span class="trade-rec-value">${entry}</span>
    </div>
    <div class="trade-rec-row">
      <span class="trade-rec-label">Stop Loss</span>
      <span class="trade-rec-value">${sl}</span>
    </div>
    <div class="trade-rec-row">
      <span class="trade-rec-label">Take Profit</span>
      <span class="trade-rec-value">${tp}</span>
    </div>
    <div class="trade-rec-row">
      <span class="trade-rec-label">Tamanho da posição</span>
      <span class="trade-rec-value">${size} do capital</span>
    </div>
    <div class="trade-rec-row">
      <span class="trade-rec-label">Risco estimado</span>
      <span class="trade-rec-value">${risk}</span>
    </div>
    <div class="trade-rec-row">
      <span class="trade-rec-label">Confiança dos agentes</span>
      <span class="trade-rec-value">${confPct}</span>
    </div>
    <div class="trade-rec-justification">${escapeHtml(rec.justification || '')}</div>
  `;

  // Disable confirm if no consensus or mock source
  const canConfirm = rec.agents_consensus && rec.source !== 'mock';
  if (_tradeConfirmBtn) {
    _tradeConfirmBtn.disabled = !canConfirm;
    _tradeConfirmBtn.title = canConfirm
      ? 'Confirmar execução'
      : 'Confirmar bloqueado: confiança insuficiente ou fonte mock';
  }
}

async function _tradeAnalyze() {
  // Client-side pre-flight
  const preCheck = _tradeClientGuardrails();
  if (!preCheck.ok) {
    alert('⚠️ ' + preCheck.reason);
    if (_tradeNowBtn) _tradeNowBtn.disabled = false;
    return;
  }

  _tradeOpenModal();
  if (_tradeNowBtn) _tradeNowBtn.disabled = true;

  try {
    const res = await fetch('/api/trade/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });

    // Parse com fallback — se o servidor retornar texto de erro (500, 401, etc.)
    // ao invés de JSON, capturamos o texto e exibimos mensagem útil.
    let data;
    try {
      data = await res.json();
    } catch (_parseErr) {
      const raw = await res.text().catch(() => '(sem resposta)');
      const statusMsg = res.status === 401
        ? 'Sessão expirada — recarregue o dashboard e faça login novamente.'
        : res.status === 500
        ? `Erro interno do servidor (${res.status}). Verifique os logs: ${raw.slice(0, 120)}`
        : `Resposta inesperada do servidor (HTTP ${res.status}): ${raw.slice(0, 120)}`;
      throw new Error(statusMsg);
    }

    _currentRecId = data.recommendation_id;
    _currentRec   = data.recommendation;

    _tradeRenderGuardrails(data.guardrails?.checks || []);
    _tradeRenderRecommendation(data.recommendation, data.is_paper);
    _tradeShowPanel('trade-modal-recommendation');
  } catch (err) {
    const resultEl = document.getElementById('trade-result-content');
    if (resultEl) {
      resultEl.innerHTML =
        `<p class="trade-result-fail">❌ Erro ao consultar agentes: ${escapeHtml(String(err))}</p>`;
      _tradeShowPanel('trade-modal-result');
    }
    if (_tradeNowBtn) _tradeNowBtn.disabled = false;
  }
}

async function _tradeExecute() {
  if (!_currentRecId) return;
  if (_tradeConfirmBtn) _tradeConfirmBtn.disabled = true;
  _tradeShowPanel('trade-modal-loading');

  try {
    const res = await fetch('/api/trade/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recommendation_id: _currentRecId, confirmed: true }),
    });
    const data = await res.json();
    const resultEl = document.getElementById('trade-result-content');
    if (resultEl) {
      if (data.status === 'submitted') {
        resultEl.innerHTML = `
          <p class="trade-result-success">✅ Ordem submetida!</p>
          <p>Order ID: <code>${escapeHtml(data.order_id || '—')}</code></p>
          <p>${escapeHtml(data.reason || '')}</p>
          ${data.is_paper ? '<p class="muted-line">⚠️ Paper mode — nenhuma ordem real foi enviada.</p>' : ''}
        `;
      } else {
        resultEl.innerHTML = `
          <p class="trade-result-fail">🚫 ${escapeHtml(data.status?.toUpperCase() || 'ERRO')}</p>
          <p>${escapeHtml(data.reason || 'Execução bloqueada.')}</p>
        `;
      }
    }
    _tradeShowPanel('trade-modal-result');
  } catch (err) {
    const resultEl = document.getElementById('trade-result-content');
    if (resultEl) resultEl.innerHTML = `<p class="trade-result-fail">❌ Erro na execução: ${escapeHtml(String(err))}</p>`;
    _tradeShowPanel('trade-modal-result');
  }
  if (_tradeNowBtn) _tradeNowBtn.disabled = false;
  // Refresh topbar after trade
  setTimeout(_mkLoadTopBar, 2000);
}

function _mkBootTradeNow() {
  // Resolve DOM refs now that the document is fully ready
  _tradeModal       = document.getElementById('trade-modal');
  _tradeModalClose  = document.getElementById('trade-modal-close');
  _tradeGuardrails  = document.getElementById('trade-guardrails');
  _tradeRecCard     = document.getElementById('trade-rec-card');
  _tradeConfirmBtn  = document.getElementById('trade-confirm-btn');
  _tradeCancelBtn   = document.getElementById('trade-cancel-btn');
  _tradeResultClose = document.getElementById('trade-result-close');
  _tradeNowBtn      = document.getElementById('trade-now-btn');

  if (_tradeNowBtn)      _tradeNowBtn.addEventListener('click', _tradeAnalyze);
  if (_tradeModalClose)  _tradeModalClose.addEventListener('click', _tradeCloseModal);
  if (_tradeCancelBtn)   _tradeCancelBtn.addEventListener('click', _tradeCloseModal);
  if (_tradeConfirmBtn)  _tradeConfirmBtn.addEventListener('click', _tradeExecute);
  if (_tradeResultClose) _tradeResultClose.addEventListener('click', _tradeCloseModal);
  if (_tradeModal)       _tradeModal.addEventListener('click', e => { if (e.target === _tradeModal) _tradeCloseModal(); });
}

// ============================================================
// LIVE TRADING PANEL
// ============================================================

let _liveChart          = null;  // lightweight-charts IChartApi
let _liveCandleSeries   = null;  // ISeriesApi (CandlestickSeries)
let _liveVolumeSeries   = null;  // ISeriesApi (HistogramSeries)
let _liveWs             = null;  // WebSocket to /ws/live
let _liveWsActive       = false;
let _livePrices         = {};    // coin → price from WS
let _livePositionLines  = {};    // symbol → price-line on chart
let _liveLastCandles    = [];    // last fetched candles array
let _liveCurrentSymbol  = 'BTC';
let _liveCurrentTf      = '15m';
let _liveLastPrice      = null;
let _liveChartBooted    = false;

// DOM refs (resolved in _bootLiveChart)
let _liveDot, _livePriceEl, _liveChangeEl, _liveStatusEl,
    _livePosList, _livePosCount, _liveEquityStrip,
    _liveSymbolSel, _liveTfSel, _liveLegend;

// ── Helpers ─────────────────────────────────────────────────
function _liveSetStatus(msg, ok = true) {
  if (_liveStatusEl) _liveStatusEl.textContent = msg;
  if (_liveDot) {
    _liveDot.classList.toggle('disconnected', !ok);
  }
}

function _liveFmtMoney(n) {
  const abs = Math.abs(n);
  if (abs >= 1e6) return (n / 1e6).toFixed(2) + 'M';
  if (abs >= 1e3) return (n / 1e3).toFixed(1) + 'k';
  return n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function _liveRenderLegend(c) {
  if (!_liveLegend || !c) return;
  _liveLegend.innerHTML =
    `O <b>${_liveFmtMoney(c.open)}</b>  H <b>${_liveFmtMoney(c.high)}</b>  ` +
    `L <b>${_liveFmtMoney(c.low)}</b>  C <b>${_liveFmtMoney(c.close)}</b>  ` +
    `Vol ${_liveFmtMoney(c.volume)}`;
}

// ── Chart initialization ─────────────────────────────────────
function _initLightweightChart() {
  const container = document.getElementById('live-chart');
  if (!container) return false;
  if (typeof LightweightCharts === 'undefined') {
    _liveSetStatus('lightweight-charts não carregado', false);
    return false;
  }
  container.innerHTML = '';

  _liveChart = LightweightCharts.createChart(container, {
    layout: {
      background: { type: 'solid', color: '#060d1c' },
      textColor: '#7a90bb',
      fontSize: 11,
    },
    grid: {
      vertLines: { color: '#0e1a30' },
      horzLines: { color: '#0e1a30' },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
    },
    rightPriceScale: {
      borderColor: '#1a2540',
      scaleMargins: { top: 0.1, bottom: 0.25 },
    },
    timeScale: {
      borderColor: '#1a2540',
      timeVisible: true,
      secondsVisible: false,
    },
    width:  container.clientWidth,
    height: container.clientHeight || 500,
  });

  _liveCandleSeries = _liveChart.addCandlestickSeries({
    upColor:   '#26d07c',
    downColor: '#e94560',
    borderUpColor:   '#26d07c',
    borderDownColor: '#e94560',
    wickUpColor:   '#26d07c',
    wickDownColor: '#e94560',
  });

  _liveVolumeSeries = _liveChart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: 'vol',
  });
  _liveChart.priceScale('vol').applyOptions({
    scaleMargins: { top: 0.8, bottom: 0 },
  });

  // Crosshair tooltip
  _liveChart.subscribeCrosshairMove(({ seriesData }) => {
    const candle = seriesData.get(_liveCandleSeries);
    _liveRenderLegend(candle || (_liveLastCandles.length ? _liveLastCandles[_liveLastCandles.length - 1] : null));
  });

  // Resize observer
  new ResizeObserver(() => {
    if (_liveChart && container) {
      _liveChart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
    }
  }).observe(container);

  return true;
}

// ── Fetch OHLCV and render ───────────────────────────────────
async function _liveLoadCandles(symbol, tf) {
  _liveSetStatus('Carregando candles…');
  try {
    const res = await fetch(`/api/hl/candles?symbol=${encodeURIComponent(symbol)}&tf=${tf}&limit=200`);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    if (!data.candles || !data.candles.length) throw new Error('Sem dados');
    _liveLastCandles = data.candles;
    _liveCandleSeries.setData(data.candles);
    _liveVolumeSeries.setData(data.candles.map(c => ({
      time:  c.time,
      value: c.volume,
      color: c.close >= c.open ? 'rgba(38,208,124,0.35)' : 'rgba(233,69,96,0.35)',
    })));
    _liveChart.timeScale().fitContent();
    const last = data.candles[data.candles.length - 1];
    _liveRenderLegend(last);
    const lp = data.last_price || last.close;
    _liveUpdateTickerPrice(lp);
    _liveSetStatus('Hyperliquid · ' + symbol + ' ' + tf);
    return data.candles;
  } catch (err) {
    _liveSetStatus('Erro ao carregar: ' + err.message, false);
    return [];
  }
}

// ── Update last candle with live tick price ──────────────────
function _liveUpdateLastCandle(price) {
  if (!_liveCandleSeries || !_liveLastCandles.length) return;
  const last = _liveLastCandles[_liveLastCandles.length - 1];
  const updated = {
    time:  last.time,
    open:  last.open,
    high:  Math.max(last.high, price),
    low:   Math.min(last.low, price),
    close: price,
    volume: last.volume,
  };
  _liveLastCandles[_liveLastCandles.length - 1] = updated;
  _liveCandleSeries.update(updated);
  _liveRenderLegend(updated);
}

// ── Ticker price update ──────────────────────────────────────
function _liveUpdateTickerPrice(price) {
  if (!_livePriceEl) return;
  const prev = _liveLastPrice;
  _liveLastPrice = price;
  _livePriceEl.textContent = '$' + price.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (_liveChangeEl && prev && prev !== price) {
    const diff = price - prev;
    const pct  = ((diff / prev) * 100).toFixed(3);
    _liveChangeEl.textContent = (diff >= 0 ? '+' : '') + pct + '%';
    _liveChangeEl.className   = 'live-ticker-change ' + (diff >= 0 ? 'up' : 'down');
  }
}

// ── Draw position entry lines on chart ──────────────────────
function _liveDrawPositionLines(positions) {
  if (!_liveCandleSeries) return;
  // Remove previous lines
  Object.values(_livePositionLines).forEach(line => {
    try { _liveCandleSeries.removePriceLine(line); } catch (_) {}
  });
  _livePositionLines = {};
  (positions || []).forEach(p => {
    if (!p.is_paper && !p.entry_price) return;
    const sym = (p.symbol || '').toUpperCase();
    if (sym !== _liveCurrentSymbol) return;
    try {
      const line = _liveCandleSeries.createPriceLine({
        price: p.entry_price,
        color: p.side === 'SHORT' ? '#e94560' : '#26d07c',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: `${p.side} entry`,
      });
      _livePositionLines[sym + '_' + p.side] = line;
    } catch (_) {}
  });
}

// ── Render open positions sidebar ────────────────────────────
function _liveRenderPositions(positions) {
  if (!_livePosList) return;
  if (!positions || !positions.length) {
    _livePosList.innerHTML = '<div class="muted-line live-pos-empty">Sem posições abertas</div>';
    if (_livePosCount) _livePosCount.textContent = '0';
    if (_liveEquityStrip) _liveEquityStrip.textContent = '';
    return;
  }
  if (_livePosCount) _livePosCount.textContent = String(positions.length);

  let totalPnl = 0;
  _livePosList.innerHTML = positions.map(p => {
    const pnl   = Number(p.pnl_usd || 0);
    const pnlPct = Number(p.pnl_pct || 0);
    totalPnl += pnl;
    const pnlClass  = pnl > 0 ? 'up' : pnl < 0 ? 'down' : '';
    const cardClass = pnl > 0 ? 'pnl-up' : pnl < 0 ? 'pnl-down' : '';
    const sideClass = (p.side || 'LONG').toLowerCase();
    const mark  = Number(p.mark_price || p.entry_price || 0);
    const entry = Number(p.entry_price || 0);
    const badge = p.is_paper ? '<span style="font-size:0.65rem;color:#888;margin-left:4px">PAPER</span>' : '';
    return `<div class="live-pos-card ${cardClass}" data-sym="${escapeHtml(p.symbol)}" data-side="${escapeHtml(p.side || 'LONG')}">
      <div class="live-pos-top">
        <span class="live-pos-sym">${escapeHtml(p.symbol)}${badge}</span>
        <span class="live-pos-side ${sideClass}">${escapeHtml(p.side || 'LONG')}</span>
      </div>
      <div class="live-pos-pnl ${pnlClass}">${pnl >= 0 ? '+' : ''}$${_liveFmtMoney(pnl)} <span style="font-size:0.72rem">(${pnl >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%)</span></div>
      <div class="live-pos-row"><span>Entrada</span><span>$${_liveFmtMoney(entry)}</span></div>
      <div class="live-pos-row"><span>Mark</span><span>$${_liveFmtMoney(mark)}</span></div>
      <div class="live-pos-row"><span>Tamanho</span><span>${Number(p.size).toFixed(6)}</span></div>
      ${p.is_paper ? `<div class="live-pos-actions"><button class="live-pos-close-btn" data-sym="${escapeHtml(p.symbol)}" data-side="${escapeHtml(p.side || 'LONG')}">✕ Fechar</button></div>` : ''}
    </div>`;
  }).join('');

  // Wire close buttons
  _livePosList.querySelectorAll('.live-pos-close-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const sym = btn.dataset.sym, side = btn.dataset.side;
      if (!confirm(`Fechar ${sym} ${side}?`)) return;
      btn.disabled = true;
      const hdrs = { 'Content-Type': 'application/json' };
      const tok = getDashboardToken(); if (tok) hdrs['X-Mekka-Token'] = tok;
      try {
        const res = await fetch('/api/positions/close', {
          method: 'POST', headers: hdrs, credentials: 'include',
          body: JSON.stringify({ symbol: sym, side }),
        });
        const d = await res.json();
        if (res.ok && d.status === 'closed') {
          btn.closest('.live-pos-card').style.opacity = '0.3';
        } else {
          alert('Erro: ' + (d.error || JSON.stringify(d)));
          btn.disabled = false;
        }
      } catch (e) { alert('Falha: ' + e); btn.disabled = false; }
    });
  });

  if (_liveEquityStrip) {
    const cls = totalPnl >= 0 ? 'color:#26d07c' : 'color:#e94560';
    _liveEquityStrip.innerHTML = `PnL Total: <strong style="${cls}">${totalPnl >= 0 ? '+' : ''}$${_liveFmtMoney(totalPnl)}</strong>`;
  }
}

// ── WebSocket to /ws/live ─────────────────────────────────────
function _liveConnectWs() {
  // If global WS is already alive, reuse it — no second connection needed.
  // Register the live-page handler via _liveChartBooted flag (checked in _gWs.onmessage).
  if (_gWs && _gWs.readyState < 2) {
    _liveWsActive = true;
    if (_liveDot) _liveDot.classList.remove('disconnected');
    _liveSetStatus('Conectado — Hyperliquid ao vivo');
    _liveWs = _gWs; // keep reference for legacy code that checks _liveWs
    return;
  }

  if (_liveWs && _liveWs.readyState < 2) return; // already open/connecting
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  _liveWs = new WebSocket(`${proto}//${location.host}/ws/live`);

  _liveWs.onopen = () => {
    _liveWsActive = true;
    if (_liveDot) _liveDot.classList.remove('disconnected');
    _liveSetStatus('Conectado — Hyperliquid ao vivo');
  };

  _liveWs.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (data.type !== 'live_tick') return;
      _livePrices = data.prices || {};
      // Update current symbol price
      const price = _livePrices[_liveCurrentSymbol];
      if (price) {
        _liveUpdateTickerPrice(price);
        _liveUpdateLastCandle(price);
      }
      // Update positions
      const positions = data.positions || [];
      _liveRenderPositions(positions);
      _liveDrawPositionLines(positions);
    } catch (_) {}
  };

  _liveWs.onclose = () => {
    _liveWsActive = false;
    if (_liveDot) _liveDot.classList.add('disconnected');
    _liveSetStatus('Desconectado — reconectando em 5s…', false);
    setTimeout(_liveConnectWs, 5000);
  };

  _liveWs.onerror = () => {
    _liveSetStatus('Erro no WebSocket', false);
  };
}

// ── Main boot function ───────────────────────────────────────
async function _bootLiveChart() {
  // Resolve DOM refs
  _liveDot         = document.getElementById('live-dot');
  _livePriceEl     = document.getElementById('live-price');
  _liveChangeEl    = document.getElementById('live-change');
  _liveStatusEl    = document.getElementById('live-status');
  _livePosList     = document.getElementById('live-positions-list');
  _livePosCount    = document.getElementById('live-pos-count');
  _liveEquityStrip = document.getElementById('live-equity-strip');
  _liveSymbolSel   = document.getElementById('live-symbol-select');
  _liveTfSel       = document.getElementById('live-tf-select');
  _liveLegend      = document.getElementById('live-legend');

  if (!document.getElementById('live-chart')) return;

  // Init chart
  if (!_initLightweightChart()) return;
  _liveChartBooted = true;

  // Load initial candles
  await _liveLoadCandles(_liveCurrentSymbol, _liveCurrentTf);

  // Connect WebSocket
  _liveConnectWs();

  // Symbol change
  if (_liveSymbolSel) {
    _liveSymbolSel.addEventListener('change', async () => {
      _liveCurrentSymbol = _liveSymbolSel.value;
      // Clear position lines for new symbol
      Object.values(_livePositionLines).forEach(l => {
        try { _liveCandleSeries.removePriceLine(l); } catch (_) {}
      });
      _livePositionLines = {};
      _liveLastPrice = null;
      await _liveLoadCandles(_liveCurrentSymbol, _liveCurrentTf);
    });
  }

  // Timeframe change
  if (_liveTfSel) {
    _liveTfSel.addEventListener('change', async () => {
      _liveCurrentTf = _liveTfSel.value;
      await _liveLoadCandles(_liveCurrentSymbol, _liveCurrentTf);
    });
  }
}

// ── Boot only when "live" page becomes active ────────────────
function _ensureLiveChartBooted() {
  if (!_liveChartBooted) {
    _bootLiveChart().catch(e => console.error('[live] boot error:', e));
  }
}

// ── Trading Mode Toggles (Super Agressivo / Altcoins) ───────────
function _applyModeStatus(id, statusId, enabled) {
  const toggle = document.getElementById(id);
  const statusEl = document.getElementById(statusId);
  if (toggle) toggle.checked = enabled;
  if (statusEl) {
    statusEl.textContent = enabled ? 'ON' : 'OFF';
    statusEl.classList.toggle('on', enabled);
  }
}

async function _bootTradingModes() {
  const superToggle = document.getElementById('toggle-super-aggressive');
  const altcoinsToggle = document.getElementById('toggle-altcoins');
  const saveStatus = document.getElementById('mode-save-status');

  // Load current settings from server
  try {
    const _settingsHeaders = { 'Content-Type': 'application/json' };
    const _tok = getDashboardToken();
    if (_tok) _settingsHeaders['X-Mekka-Token'] = _tok;
    const res = await fetch('/api/settings', { cache: 'no-store', credentials: 'include', headers: _settingsHeaders });
    if (res.ok) {
      const cfg = await res.json();
      _applyModeStatus('toggle-super-aggressive', 'status-super-aggressive', !!cfg.super_aggressive);
      _applyModeStatus('toggle-altcoins', 'status-altcoins', !!cfg.altcoins_enabled);
    }
  } catch (_) {}

  async function _saveSetting(key, value) {
    if (saveStatus) { saveStatus.textContent = 'Salvando…'; saveStatus.style.opacity = '1'; }
    try {
      const body = {};
      body[key] = value;
      const _hdrs = { 'Content-Type': 'application/json' };
      const _tok2 = getDashboardToken();
      if (_tok2) _hdrs['X-Mekka-Token'] = _tok2;
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: _hdrs,
        credentials: 'include',
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (res.ok) {
        if (saveStatus) {
          saveStatus.textContent = '✅ Salvo';
          setTimeout(() => { if (saveStatus) saveStatus.style.opacity = '0'; }, 2000);
        }
        return data.settings;
      }
    } catch (err) {
      if (saveStatus) { saveStatus.textContent = '❌ Erro ao salvar'; saveStatus.style.opacity = '1'; }
    }
    return null;
  }

  if (superToggle) {
    superToggle.addEventListener('change', async () => {
      const cfg = await _saveSetting('super_aggressive', superToggle.checked);
      if (cfg) _applyModeStatus('toggle-super-aggressive', 'status-super-aggressive', !!cfg.super_aggressive);
    });
  }
  if (altcoinsToggle) {
    altcoinsToggle.addEventListener('change', async () => {
      const cfg = await _saveSetting('altcoins_enabled', altcoinsToggle.checked);
      if (cfg) _applyModeStatus('toggle-altcoins', 'status-altcoins', !!cfg.altcoins_enabled);
    });
  }
}

// ── Global Live WebSocket — sempre conectado (topbar + posições + live page) ──
let _gWs = null;
let _gWsOn = false;

function _gWsSetBadge(on) {
  const el = document.getElementById('ftb-live-badge');
  if (!el) return;
  el.textContent = on ? '● LIVE' : '○ OFF';
  el.className = `ftb-live-badge ${on ? 'live-on' : 'live-off'}`;
}

function _gWsUpdateTopBar(positions, equity) {
  const set = (id, txt, cls) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = txt;
    el.className = cls ? `ftb-value ${cls}` : 'ftb-value';
  };
  const eq = equity && equity.equity_usd;
  if (eq != null) set('ftb-wallet-val', fmtMoney(eq));
  set('ftb-positions-val', String(positions.length || 0));
  const totalPnl = positions.reduce((s, p) => s + (Number(p.pnl_usd) || 0), 0);
  const pnlCls = totalPnl > 0 ? 'positive' : totalPnl < 0 ? 'negative' : '';
  set('ftb-daypnl-val', (totalPnl >= 0 ? '+' : '') + fmtMoney(totalPnl), pnlCls);
  const base = (eq || 10000);
  const pct = base > 0 ? (totalPnl / base * 100) : 0;
  set('ftb-daypnl-pct-val', (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%', pnlCls);
  const upEl = document.getElementById('ftb-update-val');
  if (upEl) upEl.textContent = new Date().toLocaleTimeString('pt-BR', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
}

function _gWsUpdatePositionsPanel(positions, prices) {
  if (!positionsBody) return;
  const tbody = positionsBody.querySelector('tbody');
  if (!tbody) return;
  positions.forEach((p) => {
    const sym = String(p.symbol || '').toUpperCase();
    const side = String(p.side || 'LONG').toUpperCase();
    const row = tbody.querySelector(`tr[data-sym="${sym}"][data-side="${side}"]`);
    if (!row) return;
    const mark = (prices && prices[sym]) || p.mark_price || p.entry_price || 0;
    const qty = Number(p.size || 0);
    const entry = Number(p.entry_price || 0);
    let pnl = Number(p.pnl_usd);
    if (isNaN(pnl) && entry && qty) {
      pnl = side === 'LONG' ? (mark - entry) * qty : (entry - mark) * qty;
    }
    const pnlCls = pnl > 0 ? 'pos-side-long' : (pnl < 0 ? 'pos-side-short' : '');
    const markEl = row.querySelector('.col-mark');
    const pnlEl = row.querySelector('.col-pnl');
    if (markEl) markEl.textContent = Number(mark).toFixed(2);
    if (pnlEl) {
      pnlEl.textContent = fmtMoneyDelta(pnl);
      pnlEl.className = `col-pnl ${pnlCls}`;
    }
  });
}

function _bootGlobalWs() {
  if (_gWs && _gWs.readyState < 2) return; // already open/connecting
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  _gWs = new WebSocket(`${proto}//${location.host}/ws/live`);

  _gWs.onopen = () => {
    _gWsOn = true;
    _gWsSetBadge(true);
  };

  _gWs.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (data.type !== 'live_tick') return;
      const prices = data.prices || {};
      const positions = data.positions || [];
      const equity = data.equity || {};
      _gWsUpdateTopBar(positions, equity);
      _gWsUpdatePositionsPanel(positions, prices);
      // Feed live chart page if active
      if (_liveChartBooted) {
        _livePrices = prices;
        const price = prices[_liveCurrentSymbol];
        if (price) {
          _liveUpdateTickerPrice(price);
          _liveUpdateLastCandle(price);
        }
        _liveRenderPositions(positions);
        _liveDrawPositionLines(positions);
      }
    } catch (_) {}
  };

  _gWs.onclose = () => {
    _gWsOn = false;
    _gWsSetBadge(false);
    // Update live page dot if active
    if (_liveChartBooted) {
      _liveWsActive = false;
      if (_liveDot) _liveDot.classList.add('disconnected');
      _liveSetStatus('Desconectado — reconectando em 5s…', false);
    }
    setTimeout(_bootGlobalWs, 5000);
  };

  _gWs.onerror = () => {
    _gWsSetBadge(false);
  };
}

// ── Boot all v2 features ─────────────────────────────────────
function _mkBootDashboardV2() {
  // Sync prefs from server first (async, non-blocking — nav still works immediately)
  _mkSyncPrefsFromServer().then(() => {
    // Re-apply prefs after server sync resolves (page is already showing correctly)
    try {
      let p = 'overview';
      try { p = localStorage.getItem('mekka_current_page') || 'overview'; } catch (_) {}
      if (_PAGE_SECTIONS[p]) _mkApplyWidgetPrefs(p);
    } catch (_) {}
  }).catch(() => {});

  try { _mkBootPageNav(); } catch (e) { console.error('[v2] _mkBootPageNav failed:', e); }
  try { _mkBootTopBar();  } catch (e) { console.error('[v2] _mkBootTopBar failed:', e); }
  try { _mkBootTradeNow();} catch (e) { console.error('[v2] _mkBootTradeNow failed:', e); }
  try { _bootTradingModes(); } catch (e) { console.error('[v2] _bootTradingModes failed:', e); }
  // Global WS — real-time topbar + positions across all pages
  try { _bootGlobalWs(); } catch (e) { console.error('[v2] _bootGlobalWs failed:', e); }
}

// Chart.js is loaded with `defer`, so wait for DOMContentLoaded once.
function _mkRunAllBoots() {
  const safeBoot = (fn, label) => {
    try { fn(); } catch (e) { console.error('[boot] ' + label + ' failed:', e); }
  };
  safeBoot(mountOfficeV2Panel,  'mountOfficeV2Panel');
  safeBoot(bootCharts,          'bootCharts');
  safeBoot(bootQueue,           'bootQueue');
  safeBoot(bootMarket,          'bootMarket');
  safeBoot(bootPnl,             'bootPnl');
  safeBoot(bootKillswitch,      'bootKillswitch');
  safeBoot(bootPositions,       'bootPositions');
  safeBoot(bootInternals,       'bootInternals');
  safeBoot(bootTradesTimeline,  'bootTradesTimeline');
  safeBoot(bootFunding,         'bootFunding');
  // v2 must always run — page isolation, topbar, TradeNow
  _mkBootDashboardV2();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _mkRunAllBoots);
} else {
  _mkRunAllBoots();
}
