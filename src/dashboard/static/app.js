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
    ['Runtime', overview.mode],
    ['Trading Mode', overview.trading_mode || '-'],
    ['Exchange', overview.active_exchange || '-'],
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
    // H1 fix: limpar TODOS os timers conhecidos ao esconder aba
    chartsAutoRefreshTimer         = _clearTimer(chartsAutoRefreshTimer);
    queueAutoRefreshTimer          = _clearTimer(queueAutoRefreshTimer);
    marketAutoRefreshTimer         = _clearTimer(marketAutoRefreshTimer);
    pnlAutoRefreshTimer            = _clearTimer(pnlAutoRefreshTimer);
    killswitchAutoRefreshTimer     = _clearTimer(killswitchAutoRefreshTimer);
    positionsAutoRefreshTimer      = _clearTimer(positionsAutoRefreshTimer);
    internalsAutoRefreshTimer      = _clearTimer(internalsAutoRefreshTimer);
    tradesTimelineAutoRefreshTimer = _clearTimer(tradesTimelineAutoRefreshTimer);
    fundingAutoRefreshTimer        = _clearTimer(fundingAutoRefreshTimer);
    _eqTimer                       = _clearTimer(_eqTimer);
    _riskPanelTimer                = _clearTimer(_riskPanelTimer);
    _lbTimer                       = _clearTimer(_lbTimer);
    _memoryTimer                   = _clearTimer(_memoryTimer);
    _tsSummaryTimer                = _clearTimer(_tsSummaryTimer);
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
    bootEquityCurve();
    bootRiskPanel();
    bootLeaderboard();
    bootMemory();
    bootTodaySummary();
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
  // Two additions on Overview vs the pre-merge baseline:
  //   - sec-today-summary    (codex M40) — condensed daily P&L + cycle status
  //   - sec-trading-settings (M22)       — mode preset + override toggles
  //     surfaced here too so the operator never has to dig into Settings just
  //     to change the active trading mode. The panel's HTML carries
  //     `data-page="overview settings"` to mirror this membership — keep
  //     these two lists in sync if you change either.
  overview:    ['sec-today-summary', 'sec-office', 'sec-live-market', 'sec-metrics', 'sec-trading-settings'],
  wallet:      ['sec-killswitch', 'sec-pnl', 'sec-positions', 'sec-funding'],
  performance: ['sec-equity-curve', 'sec-trades-timeline', 'sec-replay-charts', 'sec-hero-sla'],
  agents:      ['sec-layers', 'sec-agents', 'sec-internals'],
  trades:      ['sec-signals', 'sec-trades'],
  risk:        ['sec-risk-panel', 'sec-risk', 'sec-anomalies', 'sec-incident-queue'],
  logs:        ['sec-audit', 'sec-replay-player', 'sec-manual', 'sec-timeline', 'sec-symbol-timeline'],
  settings:    ['sec-trading-settings', 'sec-settings', 'sec-filters'],
  live:        ['sec-live-trading'],
  memory:      ['sec-memory'],
  leaderboard: ['sec-leaderboard'],
  reports:     ['sec-report-daily', 'sec-report-symbol', 'sec-report-backtest'],
  // Milestones 36-39 (Stories 224-243)
  backtest:    ['sec-backtest-controls', 'sec-backtest-metrics', 'sec-backtest-equity'],
  analytics:   ['sec-perf-rolling', 'sec-batman-timeline', 'sec-concentration', 'sec-debate'],
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

  // Re-carregar dados ao navegar para páginas dinâmicas
  if (pageKey === 'memory' && typeof loadMemory === 'function') loadMemory();
  if (pageKey === 'overview' && typeof loadTodaySummary === 'function') loadTodaySummary();
  if (pageKey === 'reports' && typeof bootReports === 'function') bootReports();
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

      const tradingMode = String(ovRes.trading_mode || '—').toUpperCase();
      const exchange = String(ovRes.active_exchange || '').toUpperCase();
      const modeLabel = exchange ? `${tradingMode} · ${exchange}` : tradingMode;
      set('ftb-mode-val', modeLabel);
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
  // The env badge is loaded once at boot and then refreshed lazily every
  // 60s. Changes are rare (operator edits .env and restarts) but a stale
  // badge is dangerous on a mainnet → testnet downgrade so we still poll.
  _mkLoadEnvBadge();
  setInterval(_mkLoadEnvBadge, 60000);
}

// ── Environment badge ────────────────────────────────────────
/**
 * Populate the #env-badge with the active exchange + network. Pulls
 * /api/env and reflects the result on the existing span. Three colour
 * classes are mutually exclusive: paper (cyan), testnet (orange),
 * mainnet (red, pulsing). On any error we keep the "unknown" state
 * rather than silently rendering a misleading safe label.
 */
async function _mkLoadEnvBadge() {
  const el = document.getElementById('env-badge');
  if (!el) return;
  try {
    const res = await fetch('/api/env').then(r => r.json());
    if (!res || !res.exchange) throw new Error('bad payload');
    const ex = String(res.exchange).toUpperCase();
    const net = String(res.network || 'unknown').toUpperCase();
    const mode = String(res.mode || 'unknown');
    // Label content: include both exchange and network so an operator
    // never has to remember which one is "current". Paper override is
    // shown explicitly so the operator knows the mainnet colour does
    // NOT mean live orders.
    let label;
    if (mode === 'paper') label = `${ex} · PAPER`;
    else                  label = `${ex} · ${net}`;
    el.textContent = label;
    el.title = `Exchange: ${ex}\nNetwork: ${net}\nPaper trading: ${res.paper_trading}\nLive confirmed: ${res.live_confirmed}`;
    // Reset class list before reapplying — order doesn't matter, only
    // exactly one of the four states should be present.
    el.classList.remove(
      'env-badge-unknown',
      'env-badge-paper',
      'env-badge-testnet',
      'env-badge-mainnet',
    );
    el.classList.add(`env-badge-${mode}`);
  } catch (_e) {
    // Pessimistic fallback: stay on "unknown". A grey badge is the right
    // signal when we cannot prove which network we are talking to.
    el.textContent = '??? · ???';
    el.title = 'Environment unknown — /api/env unreachable';
    el.classList.remove(
      'env-badge-paper', 'env-badge-testnet', 'env-badge-mainnet',
    );
    el.classList.add('env-badge-unknown');
  }
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
let _liveCandleRefreshTimer = null;  // periodic full candle reload (5 min)
let _liveLoadingCandles     = false;
let _liveLoadingRetryTimer  = null;

// ── Technical Indicator state ────────────────────────────────
const _liveIndActive  = { bb: false, rsi: false, macd: false };
// BB series (on main chart)
let _liveBbUpper  = null, _liveBbMiddle = null, _liveBbLower = null;
// RSI sub-chart
let _liveRsiChart = null, _liveRsiSeries = null;
// MACD sub-chart
let _liveMacdChart = null, _liveMacdLine = null, _liveMacdSignal = null, _liveMacdHist = null;
// Time scale sync unsubscribe handles
let _liveRsiUnsub = null, _liveMacdUnsub = null;

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

function _liveShowChartOverlay(msg, spinner = false) {
  let el = document.getElementById('live-chart-overlay');
  if (!el) {
    el = document.createElement('div');
    el.id = 'live-chart-overlay';
    el.className = 'live-chart-overlay';
    const wrap = document.getElementById('live-chart')?.parentElement;
    if (wrap) wrap.appendChild(el);
  }
  el.innerHTML = spinner
    ? `<span class="lco-spinner"></span><span>${msg}</span>`
    : `<span>${msg}</span>`;
  el.classList.remove('hidden');
}
function _liveHideChartOverlay() {
  const el = document.getElementById('live-chart-overlay');
  if (el) el.classList.add('hidden');
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
    width:  container.offsetWidth  || container.clientWidth  || 900,
    height: container.offsetHeight || container.clientHeight || 500,
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

  // Resize observer — guard against zero-dimension updates (display:none transition)
  new ResizeObserver(() => {
    if (_liveChart && container) {
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w > 0 && h > 0) {
        _liveChart.applyOptions({ width: w, height: h });
      }
    }
  }).observe(container);

  return true;
}

// ── Fetch OHLCV and render ───────────────────────────────────
// tf → milliseconds (used to compute startTime)
const _LIVE_TF_MS = {
  '1m':60000,'3m':180000,'5m':300000,'15m':900000,'30m':1800000,
  '1h':3600000,'2h':7200000,'4h':14400000,'8h':28800000,'12h':43200000,
  '1d':86400000,'1w':604800000
};

function _liveParseCandlesHL(raw) {
  // Hyperliquid candleSnapshot fields: t=open_ms, o, h, l, c, v
  return (raw || []).filter(r => r && r.t != null).map(r => ({
    time:   Math.floor(Number(r.t) / 1000),
    open:   parseFloat(r.o),
    high:   parseFloat(r.h),
    low:    parseFloat(r.l),
    close:  parseFloat(r.c),
    volume: parseFloat(r.v),
  })).filter(c => !isNaN(c.open) && c.time > 0);
}

function _liveParseCandlesServer(data) {
  // Server /api/hl/candles response: { candles: [{time,open,high,low,close,volume}] }
  return (data && data.candles) ? data.candles : [];
}

function _liveRenderCandleData(candles, symbol, tf, lastPrice) {
  if (!candles || !candles.length) return false;
  _liveHideChartOverlay();
  if (_liveLoadingRetryTimer) { clearTimeout(_liveLoadingRetryTimer); _liveLoadingRetryTimer = null; }
  _liveLastCandles = candles;
  _liveCandleSeries.setData(candles);
  _liveVolumeSeries.setData(candles.map(c => ({
    time:  c.time,
    value: c.volume,
    color: c.close >= c.open ? 'rgba(38,208,124,0.35)' : 'rgba(233,69,96,0.35)',
  })));
  _liveChart.timeScale().fitContent();
  const last = candles[candles.length - 1];
  _liveRenderLegend(last);
  _liveUpdateTickerPrice(lastPrice || last.close);
  _liveSetStatus('Hyperliquid · ' + symbol + ' ' + tf);
  // Re-render active indicators with fresh candle data
  _liveRenderIndicators(candles);
  return true;
}

// ════════════════════════════════════════════════════════════════
// Technical Indicators — Story 060
// ════════════════════════════════════════════════════════════════

// ── Math helpers ─────────────────────────────────────────────
function _indSMA(closes, period) {
  const out = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) { out.push(null); continue; }
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += closes[j];
    out.push(sum / period);
  }
  return out;
}

function _indEMA(data, period) {
  const k = 2 / (period + 1);
  const out = [data[0]];
  for (let i = 1; i < data.length; i++) {
    out.push(data[i] * k + out[i - 1] * (1 - k));
  }
  return out;
}

function _calcBB(candles, period = 20, mult = 2) {
  const closes = candles.map(c => c.close);
  const sma = _indSMA(closes, period);
  const result = [];
  candles.forEach((c, i) => {
    if (sma[i] === null) return;
    const slice = closes.slice(Math.max(0, i - period + 1), i + 1);
    const mean = sma[i];
    const std = Math.sqrt(slice.reduce((s, v) => s + (v - mean) ** 2, 0) / slice.length);
    result.push({ time: c.time, upper: mean + mult * std, middle: mean, lower: mean - mult * std });
  });
  return result;
}

function _calcRSI(candles, period = 14) {
  const closes = candles.map(c => c.close);
  const result = [];
  let avgGain = 0, avgLoss = 0;

  // Seed average gains/losses
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1];
    if (d > 0) avgGain += d; else avgLoss -= d;
  }
  avgGain /= period; avgLoss /= period;

  for (let i = 0; i < candles.length; i++) {
    if (i < period) continue;
    if (i === period) {
      const rs = avgGain / (avgLoss || 1e-10);
      result.push({ time: candles[i].time, value: 100 - 100 / (1 + rs) });
      continue;
    }
    const d = closes[i] - closes[i - 1];
    const g = d > 0 ? d : 0, l = d < 0 ? -d : 0;
    avgGain = (avgGain * (period - 1) + g) / period;
    avgLoss = (avgLoss * (period - 1) + l) / period;
    const rs = avgGain / (avgLoss || 1e-10);
    result.push({ time: candles[i].time, value: 100 - 100 / (1 + rs) });
  }
  return result;
}

function _calcMACD(candles, fast = 12, slow = 26, sig = 9) {
  const closes = candles.map(c => c.close);
  const emaF = _indEMA(closes, fast);
  const emaS = _indEMA(closes, slow);
  const macdLine = emaF.map((v, i) => v - emaS[i]);
  const sigLine = _indEMA(macdLine.slice(slow - 1), sig);
  const result = [];
  candles.slice(slow - 1).forEach((c, i) => {
    if (i < sig - 1) return;
    const macd = macdLine[slow - 1 + i];
    const signal = sigLine[i];
    result.push({ time: c.time, macd, signal, hist: macd - signal });
  });
  return result;
}

// ── Sub-chart factory ─────────────────────────────────────────
function _createSubChart(containerId, height = 100) {
  const el = document.getElementById(containerId);
  if (!el) return null;
  el.innerHTML = '';
  return LightweightCharts.createChart(el, {
    layout: { background: { type: 'solid', color: '#060d1c' }, textColor: '#7a90bb', fontSize: 10 },
    grid: { vertLines: { color: '#0e1a30' }, horzLines: { color: '#0e1a30' } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: '#1a2540', scaleMargins: { top: 0.1, bottom: 0.1 }, minimumWidth: 60 },
    timeScale: { borderColor: '#1a2540', timeVisible: true, secondsVisible: false },
    width: el.offsetWidth || el.parentElement.clientWidth || 700,
    height,
    handleScroll: false,
    handleScale:  false,
  });
}

function _syncSubChart(subChart, unsub) {
  // Unsubscribe previous listener
  if (unsub) { try { unsub(); } catch (_) {} }
  return _liveChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
    if (range && subChart) {
      try { subChart.timeScale().setVisibleLogicalRange(range); } catch (_) {}
    }
  });
}

// ── Init RSI sub-chart ────────────────────────────────────────
function _initRsiChart() {
  _liveRsiChart = _createSubChart('live-rsi-chart', 100);
  if (!_liveRsiChart) return;

  // RSI line
  _liveRsiSeries = _liveRsiChart.addLineSeries({ color: '#c47bff', lineWidth: 1, priceFormat: { type: 'price', precision: 1, minMove: 0.1 } });

  // Overbought / oversold reference lines (using priceLine API)
  _liveRsiSeries.createPriceLine({ price: 70, color: 'rgba(233,69,96,0.5)', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'OB' });
  _liveRsiSeries.createPriceLine({ price: 30, color: 'rgba(38,208,124,0.5)', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'OS' });

  // Crosshair → update label
  _liveRsiChart.subscribeCrosshairMove(({ seriesData }) => {
    const d = seriesData.get(_liveRsiSeries);
    const el = document.getElementById('live-rsi-val');
    if (el && d) {
      const v = d.value.toFixed(1);
      el.textContent = v;
      el.style.color = d.value > 70 ? '#e94560' : d.value < 30 ? '#26d07c' : '#c47bff';
    }
  });

  // Sync timescale with main chart
  _liveRsiUnsub = _syncSubChart(_liveRsiChart, _liveRsiUnsub);

  // Resize observer
  new ResizeObserver(() => {
    const el = document.getElementById('live-rsi-chart');
    if (_liveRsiChart && el) _liveRsiChart.applyOptions({ width: el.clientWidth });
  }).observe(document.getElementById('live-rsi-chart'));
}

// ── Init MACD sub-chart ───────────────────────────────────────
function _initMacdChart() {
  _liveMacdChart = _createSubChart('live-macd-chart', 100);
  if (!_liveMacdChart) return;

  _liveMacdHist   = _liveMacdChart.addHistogramSeries({ priceFormat: { type: 'price', precision: 4, minMove: 0.0001 } });
  _liveMacdLine   = _liveMacdChart.addLineSeries({ color: '#38bdf8', lineWidth: 1, priceFormat: { type: 'price', precision: 4, minMove: 0.0001 } });
  _liveMacdSignal = _liveMacdChart.addLineSeries({ color: '#fb923c', lineWidth: 1, priceFormat: { type: 'price', precision: 4, minMove: 0.0001 } });

  // Zero line
  _liveMacdLine.createPriceLine({ price: 0, color: 'rgba(122,144,187,0.3)', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: false });

  // Crosshair → update label
  _liveMacdChart.subscribeCrosshairMove(({ seriesData }) => {
    const d = seriesData.get(_liveMacdLine);
    const el = document.getElementById('live-macd-val');
    if (el && d) el.textContent = d.value.toFixed(4);
  });

  _liveMacdUnsub = _syncSubChart(_liveMacdChart, _liveMacdUnsub);

  new ResizeObserver(() => {
    const el = document.getElementById('live-macd-chart');
    if (_liveMacdChart && el) _liveMacdChart.applyOptions({ width: el.clientWidth });
  }).observe(document.getElementById('live-macd-chart'));
}

// ── Render helpers ────────────────────────────────────────────
function _renderLiveBB(candles) {
  if (!_liveBbUpper) {
    _liveBbUpper  = _liveChart.addLineSeries({ color: 'rgba(96,165,250,0.6)',  lineWidth: 1, priceScaleId: 'right', lastValueVisible: false, priceLineVisible: false });
    _liveBbMiddle = _liveChart.addLineSeries({ color: 'rgba(251,191,36,0.55)', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, priceScaleId: 'right', lastValueVisible: false, priceLineVisible: false });
    _liveBbLower  = _liveChart.addLineSeries({ color: 'rgba(96,165,250,0.6)',  lineWidth: 1, priceScaleId: 'right', lastValueVisible: false, priceLineVisible: false });
  }
  const bb = _calcBB(candles);
  _liveBbUpper.setData(bb.map(d => ({ time: d.time, value: d.upper  })));
  _liveBbMiddle.setData(bb.map(d => ({ time: d.time, value: d.middle })));
  _liveBbLower.setData(bb.map(d => ({ time: d.time, value: d.lower  })));
}

function _clearLiveBB() {
  if (_liveBbUpper)  { try { _liveChart.removeSeries(_liveBbUpper);  } catch (_) {} _liveBbUpper  = null; }
  if (_liveBbMiddle) { try { _liveChart.removeSeries(_liveBbMiddle); } catch (_) {} _liveBbMiddle = null; }
  if (_liveBbLower)  { try { _liveChart.removeSeries(_liveBbLower);  } catch (_) {} _liveBbLower  = null; }
}

function _renderLiveRSI(candles) {
  if (!_liveRsiChart) _initRsiChart();
  if (!_liveRsiSeries) return;
  _liveRsiSeries.setData(_calcRSI(candles));
  _liveRsiChart.timeScale().fitContent();
}

function _renderLiveMACD(candles) {
  if (!_liveMacdChart) _initMacdChart();
  if (!_liveMacdLine) return;
  const data = _calcMACD(candles);
  _liveMacdLine.setData(data.map(d => ({ time: d.time, value: d.macd   })));
  _liveMacdSignal.setData(data.map(d => ({ time: d.time, value: d.signal })));
  _liveMacdHist.setData(data.map(d => ({
    time: d.time, value: d.hist,
    color: d.hist >= 0 ? 'rgba(38,208,124,0.55)' : 'rgba(233,69,96,0.55)',
  })));
  _liveMacdChart.timeScale().fitContent();
}

// ── Master render (called after every candle load) ────────────
function _liveRenderIndicators(candles) {
  if (!candles || candles.length < 30) return;
  if (_liveIndActive.bb)   _renderLiveBB(candles);
  if (_liveIndActive.rsi)  _renderLiveRSI(candles);
  if (_liveIndActive.macd) _renderLiveMACD(candles);
}

// ── Toggle handler (called by HTML onclick) ───────────────────
function _liveToggleIndicator(ind) {
  _liveIndActive[ind] = !_liveIndActive[ind];
  const btn = document.getElementById('ind-btn-' + ind);
  if (btn) btn.classList.toggle('active', _liveIndActive[ind]);

  if (ind === 'bb') {
    if (_liveIndActive.bb) { if (_liveLastCandles.length) _renderLiveBB(_liveLastCandles); }
    else                    _clearLiveBB();
  }

  if (ind === 'rsi') {
    const wrap = document.getElementById('live-rsi-wrap');
    if (wrap) wrap.classList.toggle('hidden', !_liveIndActive.rsi);
    if (_liveIndActive.rsi && _liveLastCandles.length) {
      requestAnimationFrame(() => _renderLiveRSI(_liveLastCandles));
    } else if (!_liveIndActive.rsi && _liveRsiUnsub) {
      try { _liveRsiUnsub(); } catch (_) {}
      _liveRsiUnsub = null;
      _liveRsiChart = null; _liveRsiSeries = null;
    }
  }

  if (ind === 'macd') {
    const wrap = document.getElementById('live-macd-wrap');
    if (wrap) wrap.classList.toggle('hidden', !_liveIndActive.macd);
    if (_liveIndActive.macd && _liveLastCandles.length) {
      requestAnimationFrame(() => _renderLiveMACD(_liveLastCandles));
    } else if (!_liveIndActive.macd && _liveMacdUnsub) {
      try { _liveMacdUnsub(); } catch (_) {}
      _liveMacdUnsub = null;
      _liveMacdChart = null; _liveMacdLine = null; _liveMacdSignal = null; _liveMacdHist = null;
    }
  }
}

async function _liveLoadCandles(symbol, tf) {
  _liveSetStatus('Carregando candles…');
  const limit = 200;
  const nowMs = Date.now();
  const startMs = nowMs - limit * (_LIVE_TF_MS[tf] || 900000);

  // ── Attempt 1: direct Hyperliquid REST API (browser → Hyperliquid, no server hop) ──
  try {
    const res = await fetch('https://api.hyperliquid.xyz/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'candleSnapshot',
        req: { coin: symbol, interval: tf, startTime: startMs, endTime: nowMs },
      }),
    });
    if (res.ok) {
      const raw = await res.json();
      const candles = _liveParseCandlesHL(raw);
      if (candles.length) {
        _liveRenderCandleData(candles, symbol, tf, null);
        return candles;
      }
    }
  } catch (_) { /* fallback below */ }

  // ── Attempt 2: server-side proxy endpoint (/api/hl/candles) ──
  try {
    const res2 = await fetch(`/api/hl/candles?symbol=${encodeURIComponent(symbol)}&tf=${tf}&limit=${limit}`);
    if (res2.ok) {
      const data = await res2.json();
      const candles = _liveParseCandlesServer(data);
      if (candles.length) {
        _liveRenderCandleData(candles, symbol, tf, data.last_price);
        return candles;
      }
    }
  } catch (_) { /* fallback below */ }

  // ── Attempt 3: Binance public API (browser direct, CORS-friendly) ──
  try {
    // Map Hyperliquid symbol → Binance symbol (e.g. "BTC" → "BTCUSDT", "ETH-PERP" → "ETHUSDT")
    const binanceSym = symbol.replace(/-PERP$/, '').replace(/-USD$/, '') + 'USDT';
    // Map HL tf → Binance interval (most match: "15m","1h","4h","1d")
    const binanceInterval = tf;
    const binRes = await fetch(
      `https://api.binance.com/api/v3/klines?symbol=${encodeURIComponent(binanceSym)}&interval=${encodeURIComponent(binanceInterval)}&limit=${limit}`
    );
    if (binRes.ok) {
      const binRaw = await binRes.json();
      // Binance klines: [openTime, open, high, low, close, volume, ...]
      const candles = (binRaw || []).map(k => ({
        time:   Math.floor(Number(k[0]) / 1000),
        open:   parseFloat(k[1]),
        high:   parseFloat(k[2]),
        low:    parseFloat(k[3]),
        close:  parseFloat(k[4]),
        volume: parseFloat(k[5]),
      })).filter(c => !isNaN(c.open) && c.time > 0);
      if (candles.length) {
        const lastC = candles[candles.length - 1];
        _liveRenderCandleData(candles, binanceSym, tf, lastC.close);
        _liveSetStatus('Binance · ' + binanceSym + ' ' + tf + ' (fallback)');
        return candles;
      }
    }
  } catch (_) { /* fallthrough */ }

  // ── All sources failed ──
  if (!_liveLoadingRetryTimer) {
    _liveLoadingRetryTimer = setTimeout(() => {
      _liveLoadingRetryTimer = null;
      if (_liveChartBooted && _liveLastCandles.length === 0) {
        _liveLoadCandles(_liveCurrentSymbol, _liveCurrentTf).catch(() => {});
      }
    }, 8000);
  }
  _liveSetStatus('Sem dados de candles — tentando novamente em 8s…', false);
  _liveShowChartOverlay('📡 Aguardando dados de mercado…', true);
  return [];
}

// ── Update last candle with live tick price ──────────────────
function _liveUpdateLastCandle(price) {
  if (!_liveCandleSeries || !_liveLastCandles.length) return;

  // ── Candle rollover: detect se o período atual virou ──────────
  // Se o timestamp "canônico" do período atual é maior que o time
  // da última candle, abrimos uma nova candle em vez de atualizar.
  const tfMs  = _LIVE_TF_MS[_liveCurrentTf] || 900_000;
  const tfSec = tfMs / 1000;
  const nowSec = Math.floor(Date.now() / 1000);
  const periodTime = Math.floor(nowSec / tfSec) * tfSec; // início do período atual (UTC-alinhado)
  const last = _liveLastCandles[_liveLastCandles.length - 1];

  if (periodTime > last.time) {
    // Nova candle — o período girou (ex: nova candle de 15m abriu)
    const newCandle = {
      time:   periodTime,
      open:   price,
      high:   price,
      low:    price,
      close:  price,
      volume: 0,
    };
    _liveLastCandles.push(newCandle);
    // Mantém janela máxima de 500 candles em memória
    if (_liveLastCandles.length > 500) _liveLastCandles.shift();
    try { _liveCandleSeries.update(newCandle); } catch (_) {}
    _liveRenderLegend(newCandle);
  } else {
    // Mesma candle — atualiza OHLCV
    const updated = {
      time:   last.time,
      open:   last.open,
      high:   Math.max(last.high, price),
      low:    Math.min(last.low, price),
      close:  price,
      volume: last.volume,
    };
    _liveLastCandles[_liveLastCandles.length - 1] = updated;
    try { _liveCandleSeries.update(updated); } catch (_) {}
    _liveRenderLegend(updated);
  }
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

// ── Draw position entry + SL/TP lines on chart ──────────────
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
    const entry = Number(p.entry_price || 0);
    const isShort = String(p.side || '').toUpperCase() === 'SHORT';
    const entryColor = isShort ? '#e94560' : '#26d07c';

    // ── Linha de entrada ──
    try {
      const entryLine = _liveCandleSeries.createPriceLine({
        price: entry,
        color: entryColor,
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: `${p.side} entry`,
      });
      _livePositionLines[sym + '_' + p.side + '_entry'] = entryLine;
    } catch (_) {}

    // ── Linha de Stop Loss (vermelha pontilhada) ──
    const sl = Number(p.sl_price || p.stop_loss || 0);
    if (sl > 0) {
      const slDistPct = entry > 0 ? Math.abs((sl - entry) / entry * 100).toFixed(2) : '';
      try {
        const slLine = _liveCandleSeries.createPriceLine({
          price: sl,
          color: '#ff4757',
          lineWidth: 2,
          lineStyle: LightweightCharts.LineStyle.Dotted,
          axisLabelVisible: true,
          title: `SL${slDistPct ? ' −' + slDistPct + '%' : ''}`,
        });
        _livePositionLines[sym + '_' + p.side + '_sl'] = slLine;
      } catch (_) {}
    }

    // ── Linha de Take Profit (verde pontilhada) ──
    const tp = Number(p.tp_price || p.take_profit || 0);
    if (tp > 0) {
      const tpDistPct = entry > 0 ? Math.abs((tp - entry) / entry * 100).toFixed(2) : '';
      try {
        const tpLine = _liveCandleSeries.createPriceLine({
          price: tp,
          color: '#2ed573',
          lineWidth: 2,
          lineStyle: LightweightCharts.LineStyle.Dotted,
          axisLabelVisible: true,
          title: `TP${tpDistPct ? ' +' + tpDistPct + '%' : ''}`,
        });
        _livePositionLines[sym + '_' + p.side + '_tp'] = tpLine;
      } catch (_) {}
    }
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
      ${(() => {
        const sl = Number(p.sl_price || p.stop_loss || 0);
        const tp = Number(p.tp_price || p.take_profit || 0);
        const slDist = (sl > 0 && entry > 0) ? Math.abs((sl - entry) / entry * 100).toFixed(2) : null;
        const tpDist = (tp > 0 && entry > 0) ? Math.abs((tp - entry) / entry * 100).toFixed(2) : null;
        let rows = '';
        if (sl > 0) rows += `<div class="live-pos-row live-pos-sl"><span>🛑 SL${slDist ? ' (−'+slDist+'%)' : ''}</span><span>$${_liveFmtMoney(sl)}</span></div>`;
        if (tp > 0) rows += `<div class="live-pos-row live-pos-tp"><span>🎯 TP${tpDist ? ' (+'+tpDist+'%)' : ''}</span><span>$${_liveFmtMoney(tp)}</span></div>`;
        return rows;
      })()}
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
    _liveWs = _gWs; // keep reference for legacy code that checks _liveWs
    if (_gWs.readyState === WebSocket.OPEN) {
      // Already connected — update live status immediately
      _liveWsActive = true;
      if (_liveDot) _liveDot.classList.remove('disconnected');
      _liveSetStatus('Conectado — Hyperliquid ao vivo');
    } else {
      // Still connecting (readyState=0) — wait for onopen to fire
      _liveSetStatus('Conectando…');
    }
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

  // Double-RAF: first frame removes display:none, second frame lets the
  // browser complete layout so container.offsetWidth/clientHeight are non-zero.
  // Falls back to a 60ms timeout as final safety net for slower devices.
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  // Extra guard: if container still has no height after double-RAF, wait a bit more.
  const _chartContainerCheck = document.getElementById('live-chart');
  if (_chartContainerCheck && _chartContainerCheck.clientHeight === 0) {
    await new Promise(r => setTimeout(r, 60));
  }

  // Init chart
  if (!_initLightweightChart()) return;
  _liveChartBooted = true;

  // Load initial candles
  await _liveLoadCandles(_liveCurrentSymbol, _liveCurrentTf);

  // Connect WebSocket
  _liveConnectWs();

  // ── Refresh periódico de candles (5 min) ──────────────────────
  // Recarrega todo o histórico do servidor para manter o gráfico
  // sincronizado com o exchange mesmo sem o WS de preços.
  if (_liveCandleRefreshTimer) clearInterval(_liveCandleRefreshTimer);
  _liveCandleRefreshTimer = setInterval(() => {
    if (_liveChartBooted && document.visibilityState !== 'hidden') {
      _liveLoadCandles(_liveCurrentSymbol, _liveCurrentTf).catch(() => {});
    }
  }, 5 * 60 * 1000); // 5 minutos

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
      // Reinicia timer para o novo símbolo
      if (_liveCandleRefreshTimer) clearInterval(_liveCandleRefreshTimer);
      _liveCandleRefreshTimer = setInterval(() => {
        if (_liveChartBooted && document.visibilityState !== 'hidden') {
          _liveLoadCandles(_liveCurrentSymbol, _liveCurrentTf).catch(() => {});
        }
      }, 5 * 60 * 1000);
      await _liveLoadCandles(_liveCurrentSymbol, _liveCurrentTf);
    });
  }

  // Timeframe change
  if (_liveTfSel) {
    _liveTfSel.addEventListener('change', async () => {
      _liveCurrentTf = _liveTfSel.value;
      // Reinicia timer para o novo timeframe
      if (_liveCandleRefreshTimer) clearInterval(_liveCandleRefreshTimer);
      _liveCandleRefreshTimer = setInterval(() => {
        if (_liveChartBooted && document.visibilityState !== 'hidden') {
          _liveLoadCandles(_liveCurrentSymbol, _liveCurrentTf).catch(() => {});
        }
      }, 5 * 60 * 1000);
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

// ── Global Mode (preset selector that drives /api/mode) ──────────────
/**
 * Render the three preset buttons (conservative/balanced/aggressive)
 * inside #global-mode-buttons, wire each click to POST /api/mode, and
 * keep the active button highlighted by polling /api/mode on a minimal
 * interval. This is the bridge between the dashboard v1 toggles
 * (super_aggressive / altcoins) and the office_v2 preset system: both
 * mechanisms now coexist on the same panel so the operator can see
 * what's active without bouncing between two UIs.
 *
 * Server contract (from src/config/runtime_mode.py):
 *   GET /api/mode  → { mode: "balanced", modes: [{id,label,description,active}, ...] }
 *   POST /api/mode { mode: "aggressive" } → 200 with new params
 */
async function _bootGlobalMode() {
  const container = document.getElementById('global-mode-buttons');
  if (!container) return;

  function render(modes, active) {
    container.innerHTML = '';
    (modes || []).forEach(m => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `global-mode-btn ${m.id === active ? 'is-active' : ''}`;
      btn.dataset.modeId = m.id;
      btn.title = m.description || '';
      btn.innerHTML = `
        <span class="gmb-label">${m.label || m.id}</span>
        <span class="gmb-desc">${m.description || ''}</span>
      `;
      btn.addEventListener('click', () => _setGlobalMode(m.id));
      container.appendChild(btn);
    });
  }

  async function loadAndRender() {
    try {
      const res = await fetch('/api/mode', { cache: 'no-store' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      // /api/mode payload shape uses either `modes` (full list with
      // labels/descriptions/active flag) or just `mode` (string). Be
      // forgiving of both so a server rolling back the runtime_mode
      // change doesn't break the UI.
      const list = Array.isArray(data.modes) && data.modes.length
        ? data.modes
        : ['conservative', 'balanced', 'aggressive'].map(id => ({ id, label: id, description: '' }));
      render(list, data.mode);
    } catch (_e) {
      // On error, still render the three buttons so the user has SOME
      // way to drive the mode. Without an active marker.
      const fallback = ['conservative', 'balanced', 'aggressive']
        .map(id => ({ id, label: id, description: '' }));
      render(fallback, null);
    }
  }

  async function _setGlobalMode(modeId) {
    const saveStatus = document.getElementById('mode-save-status');
    if (saveStatus) { saveStatus.textContent = `Mudando para ${modeId}…`; saveStatus.style.opacity = '1'; }
    try {
      const res = await fetch('/api/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: modeId }),
        credentials: 'include',
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      if (saveStatus) {
        saveStatus.textContent = `✅ Modo global: ${modeId}`;
        setTimeout(() => { if (saveStatus) saveStatus.style.opacity = '0'; }, 2500);
      }
      await loadAndRender();
    } catch (e) {
      if (saveStatus) { saveStatus.textContent = `❌ Falha: ${e.message}`; saveStatus.style.opacity = '1'; }
    }
  }

  await loadAndRender();
  // Refresh every 30s so a CLI/Telegram-driven mode change reflects in
  // the UI without a page reload.
  setInterval(loadAndRender, 30000);
}

// ── Global Live WebSocket — sempre conectado (topbar + posições + live page) ──
let _gWs = null;
let _gWsOn = false;
let _gWsPositionsLoading = false; // debounce para evitar loadPositions em loop

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
  // Se chegaram posições mas a tabela ainda não tem linhas → monta ela via REST
  if (positions.length > 0 && (!tbody || !tbody.rows.length)) {
    if (!_gWsPositionsLoading) {
      _gWsPositionsLoading = true;
      loadPositions().finally(() => { _gWsPositionsLoading = false; });
    }
    return;
  }
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
    // Update live page status/dot when chart page is active
    if (_liveChartBooted) {
      _liveWsActive = true;
      if (_liveDot) _liveDot.classList.remove('disconnected');
      _liveSetStatus('Conectado — Hyperliquid ao vivo');
    }
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
      // Feed live page ticker + positions panel (always, regardless of chart state)
      // Render positions panel whenever the Live page has been booted
      // (decoupled from chart state so positions appear even if chart fails)
      if (_liveChartBooted || _livePosList) {
        _liveRenderPositions(positions);
      }
      // Feed live chart page price/candle/lines only when chart is ready
      if (_liveChartBooted) {
        _livePrices = prices;
        // ── Fallback de preço: se HL WS não retornou o símbolo atual,
        // tenta derivar o preço a partir das posições abertas (mark_price)
        // ou do último close conhecido no _liveLastCandles.
        let price = prices[_liveCurrentSymbol];
        if (!price) {
          // Tenta mark_price de qualquer posição do símbolo atual
          const posMatch = positions.find(p =>
            (p.symbol || '').toUpperCase() === _liveCurrentSymbol.toUpperCase()
          );
          if (posMatch && posMatch.mark_price) {
            price = Number(posMatch.mark_price);
          } else if (_liveLastCandles.length) {
            // Usa último close como proxy (sem criar nova candle)
            price = _liveLastCandles[_liveLastCandles.length - 1].close;
          }
        }
        if (price) {
          _liveUpdateTickerPrice(price);
          _liveUpdateLastCandle(price);
        }
        // Auto-retry candles when WS delivers price but chart is empty
        if (price && _liveLastCandles.length === 0 && !_liveLoadingRetryTimer) {
          _liveLoadCandles(_liveCurrentSymbol, _liveCurrentTf).catch(() => {});
        }
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
  try { _bootGlobalMode();   } catch (e) { console.error('[v2] _bootGlobalMode failed:', e); }
  // Global WS — real-time topbar + positions across all pages
  try { _bootGlobalWs(); } catch (e) { console.error('[v2] _bootGlobalWs failed:', e); }
}

// ── Story 064 — Episodic Memory Panel ────────────────────────────────────────

async function loadMemory() {
  const grid  = document.getElementById('memory-grid');
  const feed  = document.getElementById('memory-feed');
  const chips = document.getElementById('memory-summary-chips');
  const meta  = document.getElementById('memory-meta');
  if (!grid) return;

  try {
    const res = await fetch('/api/memory/stats', { cache: 'no-store' });
    if (!res.ok) throw new Error(`http ${res.status}`);
    const d = await res.json();

    // Summary chips
    if (chips) {
      chips.innerHTML = `
        <span class="mem-chip mem-chip-total">📦 Total <strong>${d.total}</strong></span>
        <span class="mem-chip mem-chip-resolved">✅ Resolvidos <strong>${d.resolved}</strong></span>
        <span class="mem-chip mem-chip-pending">⏳ Pendentes <strong>${d.pending}</strong></span>
      `;
    }
    if (meta) {
      const ts = d.generated_at ? new Date(d.generated_at).toLocaleTimeString('pt-BR') : '—';
      meta.textContent = `Atualizado às ${ts}`;
    }

    // Cards grid — one card per (symbol, action)
    if (!d.by_symbol || d.by_symbol.length === 0) {
      grid.innerHTML = '<p class="mem-empty">Nenhum trade resolvido ainda. A memória começa a se formar após os primeiros SL/TP fechados.</p>';
    } else {
      grid.innerHTML = d.by_symbol.map((row) => {
        const wr = row.win_rate != null ? `${row.win_rate.toFixed(1)}%` : '—';
        const wrClass = row.win_rate == null ? '' : row.win_rate >= 55 ? 'wr-good' : row.win_rate >= 40 ? 'wr-mid' : 'wr-bad';
        const pnlSign = row.avg_pnl >= 0 ? '+' : '';
        const pnlClass = row.avg_pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
        const holdStr = row.avg_hold_h != null ? `${row.avg_hold_h.toFixed(1)}h` : '—';
        const dirClass = row.action === 'LONG' ? 'mem-long' : 'mem-short';
        const dirIcon  = row.action === 'LONG' ? '▲' : '▼';

        const recentHtml = (row.recent || []).map((r) => {
          const cls = r.outcome === 'WIN' ? 'mem-win' : r.outcome === 'LOSS' ? 'mem-loss' : 'mem-neutral';
          const sign = r.pnl_usd >= 0 ? '+' : '';
          const ago  = r.hours_ago != null ? `${r.hours_ago.toFixed(0)}h atrás` : '';
          return `<span class="mem-pill ${cls}" title="${ago}">${r.outcome} ${sign}$${r.pnl_usd.toFixed(2)}</span>`;
        }).join('');

        // Batman veto warning
        const vetoWarn = (row.win_rate != null && row.win_rate < 30 && row.total >= 8)
          ? '<div class="mem-veto">⚠️ Batman VETO ativo (win rate &lt; 30%)</div>'
          : (row.win_rate != null && row.win_rate < 45 && row.total >= 5)
          ? '<div class="mem-caution">⚠️ Batman CAUTION: size −20%</div>'
          : '';

        return `
          <div class="mem-card">
            <div class="mem-card-header">
              <span class="mem-symbol">${escapeHtml(row.symbol)}</span>
              <span class="mem-dir ${dirClass}">${dirIcon} ${row.action}</span>
              <span class="mem-total">${row.total} trades</span>
            </div>
            <div class="mem-stats">
              <div class="mem-stat">
                <span class="mem-label">Win Rate</span>
                <span class="mem-value ${wrClass}">${wr}</span>
              </div>
              <div class="mem-stat">
                <span class="mem-label">W/L/N</span>
                <span class="mem-value">${row.wins}/${row.losses}/${row.neutrals}</span>
              </div>
              <div class="mem-stat">
                <span class="mem-label">Avg PnL</span>
                <span class="mem-value ${pnlClass}">${pnlSign}$${row.avg_pnl.toFixed(2)}</span>
              </div>
              <div class="mem-stat">
                <span class="mem-label">Avg Hold</span>
                <span class="mem-value">${holdStr}</span>
              </div>
            </div>
            ${vetoWarn}
            <div class="mem-recent">${recentHtml || '<span class="muted-line">sem histórico recente</span>'}</div>
          </div>`;
      }).join('');
    }

    // Recent outcomes feed — flatten all entries, sort by hours_ago
    if (feed) {
      const allRecent = [];
      (d.by_symbol || []).forEach((row) => {
        (row.recent || []).forEach((r) => {
          allRecent.push({ ...r, symbol: row.symbol, action: row.action });
        });
      });
      allRecent.sort((a, b) => (a.hours_ago ?? 9999) - (b.hours_ago ?? 9999));
      if (allRecent.length === 0) {
        feed.innerHTML = '<span class="muted-line">Sem outcomes ainda.</span>';
      } else {
        feed.innerHTML = allRecent.slice(0, 20).map((r) => {
          const cls = r.outcome === 'WIN' ? 'mem-win' : r.outcome === 'LOSS' ? 'mem-loss' : 'mem-neutral';
          const sign = r.pnl_usd >= 0 ? '+' : '';
          const ago  = r.hours_ago != null ? `${r.hours_ago.toFixed(0)}h atrás` : '';
          const dir  = r.action === 'LONG' ? '▲' : '▼';
          return `<div class="mem-feed-row ${cls}">
            <span class="mem-feed-sym">${escapeHtml(r.symbol)} ${dir}</span>
            <span class="mem-feed-outcome">${r.outcome}</span>
            <span class="mem-feed-pnl">${sign}$${r.pnl_usd.toFixed(2)}</span>
            <span class="mem-feed-ago">${ago}</span>
          </div>`;
        }).join('');
      }
    }
  } catch (err) {
    if (grid) grid.innerHTML = `<p class="mem-empty">Erro ao carregar memória: ${escapeHtml(err.message)}</p>`;
  }
}

// ============================================================
// Story 077 — Equity Curve Chart
// ============================================================

let _eqChart = null, _ddChart = null, _eqTimer = null;

async function loadEquityCurve() {
  try {
    const headers = {};
    const tok = getDashboardToken();
    if (tok) headers['X-Mekka-Token'] = tok;
    const res = await fetch('/api/pnl/equity-curve', { headers });
    if (!res.ok) return;
    const d = await res.json();
    if (!d.labels || !d.labels.length) return;

    // ── Stats row ─────────────────────────────────────────────
    const statsRow = document.getElementById('eq-stats-row');
    if (statsRow) {
      const winColor = d.win_rate_30d >= 50 ? 'var(--good)' : 'var(--bad)';
      const ddColor  = d.max_drawdown_pct < -10 ? 'var(--bad)' : d.max_drawdown_pct < -5 ? '#f59e0b' : 'var(--good)';
      const cumLast  = d.cum_return_pct.length ? d.cum_return_pct[d.cum_return_pct.length - 1] : 0;
      statsRow.innerHTML = `
        <div class="eq-stat"><span class="eq-stat-lbl">Retorno Total</span><span class="eq-stat-val" style="color:${cumLast>=0?'var(--good)':'var(--bad)'}">${cumLast>=0?'+':''}${cumLast.toFixed(2)}%</span></div>
        <div class="eq-stat"><span class="eq-stat-lbl">Win Rate (30d)</span><span class="eq-stat-val" style="color:${winColor}">${d.win_rate_30d.toFixed(1)}%</span></div>
        <div class="eq-stat"><span class="eq-stat-lbl">Max Drawdown</span><span class="eq-stat-val" style="color:${ddColor}">${d.max_drawdown_pct.toFixed(2)}%</span></div>
        <div class="eq-stat"><span class="eq-stat-lbl">Sharpe (30d)</span><span class="eq-stat-val">${d.sharpe_30d != null ? d.sharpe_30d.toFixed(3) : '—'}</span></div>
        <div class="eq-stat"><span class="eq-stat-lbl">Dias Win/Loss</span><span class="eq-stat-val">${d.winning_days}W / ${d.losing_days}L</span></div>
      `;
    }

    if (typeof Chart === 'undefined') return;

    const baseColor = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#7c3aed';
    const goodColor = '#26d07c', badColor = '#e94560';

    // ── Equity chart ──────────────────────────────────────────
    const eqCanvas = document.getElementById('eq-equity-canvas');
    if (eqCanvas) {
      if (_eqChart) { _eqChart.destroy(); _eqChart = null; }
      _eqChart = new Chart(eqCanvas.getContext('2d'), {
        type: 'line',
        data: {
          labels: d.labels,
          datasets: [{
            label: 'Equity (USD)',
            data: d.equity,
            borderColor: baseColor,
            backgroundColor: baseColor + '18',
            borderWidth: 2,
            pointRadius: 0,
            fill: true,
            tension: 0.3,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } },
          scales: {
            x: { ticks: { color: '#7a90bb', maxTicksLimit: 8 }, grid: { color: '#0e1a30' } },
            y: { ticks: { color: '#7a90bb', callback: v => '$' + v.toLocaleString() }, grid: { color: '#0e1a30' } },
          },
        },
      });
    }

    // ── Drawdown chart ────────────────────────────────────────
    const ddCanvas = document.getElementById('eq-drawdown-canvas');
    if (ddCanvas) {
      if (_ddChart) { _ddChart.destroy(); _ddChart = null; }
      _ddChart = new Chart(ddCanvas.getContext('2d'), {
        type: 'bar',
        data: {
          labels: d.labels,
          datasets: [
            {
              label: 'PnL Diário ($)',
              data: d.daily_pnl,
              backgroundColor: d.daily_pnl.map(v => v >= 0 ? goodColor + 'cc' : badColor + 'cc'),
              yAxisID: 'y',
            },
            {
              label: 'Drawdown (%)',
              data: d.drawdown_pct,
              type: 'line',
              borderColor: badColor,
              backgroundColor: 'transparent',
              borderWidth: 1.5,
              pointRadius: 0,
              yAxisID: 'y2',
            },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#7a90bb' } }, tooltip: { mode: 'index', intersect: false } },
          scales: {
            x: { ticks: { color: '#7a90bb', maxTicksLimit: 8 }, grid: { color: '#0e1a30' } },
            y:  { ticks: { color: goodColor }, grid: { color: '#0e1a30' }, position: 'left' },
            y2: { ticks: { color: badColor,  callback: v => v.toFixed(1) + '%' }, grid: { display: false }, position: 'right' },
          },
        },
      });
    }
  } catch (e) {
    console.warn('[EquityCurve] load error:', e);
  }
}

function bootEquityCurve() {
  loadEquityCurve();
  _eqTimer = _clearTimer(_eqTimer);
  if (!document.hidden) {
    _eqTimer = setInterval(loadEquityCurve, 60000);  // refresh 1 min
  }
}

// ============================================================
// Story 073 — Live Risk Panel
// ============================================================

let _riskPanelTimer = null;

async function loadRiskPanel() {
  try {
    const headers = {};
    const tok = getDashboardToken();
    if (tok) headers['X-Mekka-Token'] = tok;
    const res = await fetch('/api/risk/panel', { headers });
    if (!res.ok) return;
    const d = await res.json();

    // Exposure bar
    const expBar = document.getElementById('rp-exposure-bar');
    const expVal = document.getElementById('rp-exposure-val');
    if (expBar && d.exposure) {
      const pct = Math.min(100, d.exposure.used_pct || 0);
      expBar.style.width = pct + '%';
      expBar.className = 'rp-bar' + (pct >= 90 ? ' rp-bar-danger' : pct >= 60 ? ' rp-bar-warn' : '');
      expVal.textContent = `$${(d.exposure.open_notional_usd||0).toLocaleString('en-US',{maximumFractionDigits:0})} / $${(d.exposure.cap_usd||0).toLocaleString('en-US',{maximumFractionDigits:0})} (${pct.toFixed(1)}%)`;
    }

    // Daily PnL bar
    const pnlBar = document.getElementById('rp-pnl-bar');
    const pnlVal = document.getElementById('rp-pnl-val');
    if (pnlBar && d.daily_pnl) {
      const pnlPct = d.daily_pnl.pnl_pct || 0;
      const target = d.daily_pnl.profit_target_pct || 5;
      const kill = d.daily_pnl.kill_threshold_pct || 10;
      const isPos = pnlPct >= 0;
      const barPct = Math.min(100, Math.abs(pnlPct) / Math.max(target, kill) * 100);
      pnlBar.style.width = barPct + '%';
      pnlBar.className = 'rp-bar rp-bar-pnl' + (!isPos ? ' rp-bar-danger' : pnlPct >= target ? ' rp-bar-success' : '');
      const sign = pnlPct >= 0 ? '+' : '';
      pnlVal.textContent = `${sign}$${(d.daily_pnl.pnl_usd||0).toFixed(2)} (${sign}${pnlPct.toFixed(2)}%) | target ${target}% | kill -${kill}%`;
      pnlVal.style.color = isPos ? 'var(--green)' : 'var(--red)';
    }

    // Cooldown chips
    const cdChips = document.getElementById('rp-cooldown-chips');
    if (cdChips) {
      if (!d.cooldowns || d.cooldowns.length === 0) {
        cdChips.innerHTML = '<span class="rp-chip rp-chip-ok">Nenhum</span>';
      } else {
        cdChips.innerHTML = d.cooldowns.map(c =>
          `<span class="rp-chip rp-chip-warn" title="Expira ${c.expires_utc}">${c.symbol} ${c.remaining_min.toFixed(0)}min</span>`
        ).join('');
      }
    }

    // Blacklist chips
    const blChips = document.getElementById('rp-blacklist-chips');
    if (blChips) {
      if (!d.blacklisted || d.blacklisted.length === 0) {
        blChips.innerHTML = '<span class="rp-chip rp-chip-ok">Nenhum</span>';
      } else {
        blChips.innerHTML = d.blacklisted.map(b =>
          `<span class="rp-chip rp-chip-danger" title="${b.consecutive_sl_hits} SLs consecutivos | expira ${b.expires_utc}">${b.symbol} ${b.remaining_h.toFixed(0)}h</span>`
        ).join('');
      }
    }

    // ATR grid
    const atrGrid = document.getElementById('rp-atr-grid');
    if (atrGrid && d.atrs && d.atrs.length > 0) {
      atrGrid.innerHTML = d.atrs.map(a => {
        const v = a.atr_pct != null ? a.atr_pct.toFixed(3) + '%' : '—';
        const cls = a.atr_pct == null ? '' : a.atr_pct > 4 ? 'rp-atr-high' : a.atr_pct > 2 ? 'rp-atr-mid' : 'rp-atr-low';
        return `<div class="rp-atr-item ${cls}"><span class="rp-atr-sym">${a.symbol}</span><span class="rp-atr-val">${v}</span></div>`;
      }).join('');
    }
  } catch (e) {
    console.warn('[RiskPanel] load error:', e);
  }
}

function bootRiskPanel() {
  loadRiskPanel();
  _riskPanelTimer = _clearTimer(_riskPanelTimer);
  if (!document.hidden) {
    _riskPanelTimer = setInterval(loadRiskPanel, 30000);  // refresh 30s
  }
}

let _memoryTimer = null;  // C1 fix: salvar referência para poder cancelar

function bootMemory() {
  loadMemory();
  _memoryTimer = _clearTimer(_memoryTimer);
  if (!document.hidden) {
    // C1 fix: salvar retorno de setInterval para limpar no visibilitychange
    _memoryTimer = setInterval(() => {
      const sec = document.getElementById('sec-memory');
      if (sec && !sec.classList.contains('page-section-hidden')) loadMemory();
    }, 60_000);
  }
}

// ============================================================
// Story 079 — Symbol Performance Leaderboard
// ============================================================

let _lbSortCol   = 'total_pnl_usd';
let _lbSortDir   = 'desc';   // 'asc' | 'desc'
let _lbData      = [];       // raw items cache
let _lbDays      = 90;
let _lbTimer     = null;

function _lbPnlClass(v) {
  if (v > 0) return 'lb-pnl-pos';
  if (v < 0) return 'lb-pnl-neg';
  return 'lb-pnl-zero';
}

function _lbFmt(v, prefix = '$', decimals = 2) {
  if (v == null) return '<span class="lb-sharpe-na">—</span>';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${prefix}${Math.abs(v).toFixed(decimals)}`;
}

function _lbRenderSummary(items) {
  const el = document.getElementById('lb-summary-row');
  if (!el) return;
  if (!items || items.length === 0) { el.innerHTML = ''; return; }
  const totalPnl = items.reduce((s, x) => s + (x.total_pnl_usd || 0), 0);
  const totalTrades = items.reduce((s, x) => s + (x.trades || 0), 0);
  const winners = items.filter(x => x.total_pnl_usd > 0).length;
  const losers  = items.filter(x => x.total_pnl_usd < 0).length;
  const best    = items.reduce((a, x) => x.total_pnl_usd > (a ? a.total_pnl_usd : -Infinity) ? x : a, null);
  const worst   = items.reduce((a, x) => x.total_pnl_usd < (a ? a.total_pnl_usd : Infinity) ? x : a, null);
  const sign = totalPnl >= 0 ? '+' : '';
  el.innerHTML = `
    <div class="lb-sum-item"><span class="lb-sum-label">PnL Total</span><span class="lb-sum-val ${_lbPnlClass(totalPnl)}">${sign}$${totalPnl.toFixed(2)}</span></div>
    <div class="lb-sum-item"><span class="lb-sum-label">Símbolos</span><span class="lb-sum-val">${items.length}</span></div>
    <div class="lb-sum-item"><span class="lb-sum-label">Trades</span><span class="lb-sum-val">${totalTrades}</span></div>
    <div class="lb-sum-item"><span class="lb-sum-label">Lucrativos</span><span class="lb-sum-val lb-pnl-pos">${winners}</span></div>
    <div class="lb-sum-item"><span class="lb-sum-label">Negativos</span><span class="lb-sum-val lb-pnl-neg">${losers}</span></div>
    ${best ? `<div class="lb-sum-item"><span class="lb-sum-label">Melhor</span><span class="lb-sum-val lb-pnl-pos">${best.symbol} +$${best.total_pnl_usd.toFixed(2)}</span></div>` : ''}
    ${worst ? `<div class="lb-sum-item"><span class="lb-sum-label">Pior</span><span class="lb-sum-val lb-pnl-neg">${worst.symbol} $${worst.total_pnl_usd.toFixed(2)}</span></div>` : ''}
  `;
}

function _lbRenderTable(items) {
  const tbody = document.getElementById('lb-tbody');
  const emptyEl = document.getElementById('lb-empty');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = '';
    if (emptyEl) emptyEl.classList.remove('hidden');
    return;
  }
  if (emptyEl) emptyEl.classList.add('hidden');

  // Sort
  const sorted = [...items].sort((a, b) => {
    let av = a[_lbSortCol], bv = b[_lbSortCol];
    if (av == null) av = _lbSortDir === 'desc' ? -Infinity : Infinity;
    if (bv == null) bv = _lbSortDir === 'desc' ? -Infinity : Infinity;
    return _lbSortDir === 'desc' ? bv - av : av - bv;
  });

  tbody.innerHTML = sorted.map((item, idx) => {
    const wr  = item.win_rate != null ? (item.win_rate * 100).toFixed(1) : null;
    const wrBar = wr != null
      ? `<div class="lb-win-bar">
           <div class="lb-win-track"><div class="lb-win-fill" style="width:${wr}%"></div></div>
           <span>${wr}%</span>
         </div>`
      : '<span class="lb-sharpe-na">—</span>';
    const pnlClass = _lbPnlClass(item.total_pnl_usd);
    const avgClass = _lbPnlClass(item.avg_pnl_usd);
    const sharpeVal = item.sharpe != null
      ? `<span class="${item.sharpe >= 1 ? 'lb-sharpe-pos' : item.sharpe < 0 ? 'lb-sharpe-neg' : ''}">${item.sharpe.toFixed(2)}</span>`
      : '<span class="lb-sharpe-na">—</span>';
    const bestPnl  = item.best_trade_usd  != null ? `<span class="lb-pnl-pos">+$${item.best_trade_usd.toFixed(2)}</span>`  : '—';
    const worstPnl = item.worst_trade_usd != null ? `<span class="lb-pnl-neg">$${item.worst_trade_usd.toFixed(2)}</span>` : '—';
    const sign = item.total_pnl_usd >= 0 ? '+' : '';
    return `<tr>
      <td class="lb-rank">${idx + 1}</td>
      <td class="lb-sym"><span class="lb-sym-pill">${item.symbol}</span></td>
      <td class="${pnlClass}">${sign}$${(item.total_pnl_usd||0).toFixed(2)}</td>
      <td>${wrBar}</td>
      <td>${item.trades}</td>
      <td class="${avgClass}">${item.avg_pnl_usd != null ? (item.avg_pnl_usd >= 0 ? '+' : '') + '$' + Math.abs(item.avg_pnl_usd).toFixed(2) : '—'}</td>
      <td>${sharpeVal}</td>
      <td class="lb-best">${bestPnl}</td>
      <td class="lb-worst">${worstPnl}</td>
    </tr>`;
  }).join('');

  // Update sort header indicators
  document.querySelectorAll('#lb-table .lb-sortable').forEach(th => {
    th.classList.remove('lb-sort-asc', 'lb-sort-desc');
    if (th.dataset.col === _lbSortCol) {
      th.classList.add(_lbSortDir === 'desc' ? 'lb-sort-desc' : 'lb-sort-asc');
    }
  });
}

async function loadLeaderboard(days) {
  if (days != null) _lbDays = days;
  const errorEl = document.getElementById('lb-error');
  const footerEl = document.getElementById('lb-footer');
  if (errorEl) errorEl.classList.add('hidden');

  try {
    const headers = {};
    const tok = getDashboardToken();
    if (tok) headers['X-Mekka-Token'] = tok;
    const res = await fetch(`/api/leaderboard?days=${_lbDays}`, { headers });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    _lbData = d.items || [];
    _lbRenderSummary(_lbData);
    _lbRenderTable(_lbData);
    if (footerEl) footerEl.textContent = `Atualizado ${new Date(d.generated_at).toLocaleTimeString()} · ${_lbDays}d`;
  } catch (e) {
    console.warn('[Leaderboard] load error:', e);
    if (errorEl) { errorEl.textContent = `Erro ao carregar leaderboard: ${e.message}`; errorEl.classList.remove('hidden'); }
  }
}

function _lbSetupInteractions() {
  // Sort columns
  document.querySelectorAll('#lb-table .lb-sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (_lbSortCol === col) {
        _lbSortDir = _lbSortDir === 'desc' ? 'asc' : 'desc';
      } else {
        _lbSortCol = col;
        _lbSortDir = 'desc';
      }
      _lbRenderTable(_lbData);
    });
  });

  // Days selector
  const sel = document.getElementById('lb-days-select');
  if (sel) {
    sel.addEventListener('change', () => loadLeaderboard(parseInt(sel.value, 10)));
  }

  // Refresh button
  const btn = document.getElementById('lb-refresh-btn');
  if (btn) {
    btn.addEventListener('click', () => loadLeaderboard());
  }
}

function bootLeaderboard() {
  _lbSetupInteractions();
  loadLeaderboard(_lbDays);
  _lbTimer = _clearTimer(_lbTimer);
  if (!document.hidden) {
    _lbTimer = setInterval(() => {
      const sec = document.getElementById('sec-leaderboard');
      if (sec && !sec.classList.contains('page-section-hidden')) loadLeaderboard();
    }, 120_000);  // auto-refresh 2 min
  }
}

// ============================================================
// COMMAND CENTER — Manual Trade Entry
// ============================================================
let _cmdCurrentSide = 'LONG';
let _cmdCurrentMode = 'auto';

function _cmdToggle() {
  const el = document.getElementById('cmd-center');
  const btn = document.getElementById('live-cmd-toggle');
  if (!el) return;
  el.classList.toggle('hidden');
  const open = !el.classList.contains('hidden');
  if (btn) btn.classList.toggle('active', open);
  // Sync symbol with live chart
  const sym = document.getElementById('cmd-symbol');
  const liveSym = document.getElementById('live-symbol-select');
  if (sym && liveSym && open) sym.value = liveSym.value;
  // Auto-fill entry price from last price
  _cmdFillMarketPrice();
}

function _cmdFillMarketPrice() {
  const entryEl = document.getElementById('cmd-entry');
  if (!entryEl) return;
  const sym = (document.getElementById('cmd-symbol')?.value || 'BTC').toUpperCase();
  const price = _livePrices[sym] || (_liveLastCandles.length ? _liveLastCandles[_liveLastCandles.length-1].close : null);
  if (price && !entryEl.value) entryEl.placeholder = price.toFixed(2) + ' (Market)';
}

function _cmdSetMode(mode) {
  _cmdCurrentMode = mode;
  document.getElementById('cmd-mode-auto')?.classList.toggle('active', mode === 'auto');
  document.getElementById('cmd-mode-manual')?.classList.toggle('active', mode === 'manual');
}

function _cmdSetSide(side) {
  _cmdCurrentSide = side;
  document.getElementById('cmd-side-long')?.classList.toggle('active', side === 'LONG');
  document.getElementById('cmd-side-short')?.classList.toggle('active', side === 'SHORT');
}

function _cmdSetStatus(msg, type = 'info') {
  const el = document.getElementById('cmd-status');
  if (!el) return;
  el.textContent = msg;
  el.className = `cmd-status ${type}`;
}

async function _cmdExecute() {
  const btn = document.getElementById('cmd-execute-btn');
  const symbol = document.getElementById('cmd-symbol')?.value || 'BTC';
  const size_pct = parseFloat(document.getElementById('cmd-size')?.value || 2);
  const leverage = parseInt(document.getElementById('cmd-leverage')?.value || 5);
  const sl_pct = parseFloat(document.getElementById('cmd-sl')?.value || 2);
  const tp_pct = parseFloat(document.getElementById('cmd-tp')?.value || 4);
  const entryVal = document.getElementById('cmd-entry')?.value;
  const entry_price = entryVal ? parseFloat(entryVal) : null;

  if (!symbol || isNaN(size_pct) || isNaN(leverage)) {
    _cmdSetStatus('Preencha todos os campos obrigatórios.', 'error');
    return;
  }

  if (btn) btn.disabled = true;
  _cmdSetStatus('Enviando ordem…', 'info');

  try {
    const res = await fetch('/api/trade/manual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol,
        side: _cmdCurrentSide,
        size_pct,
        leverage,
        sl_pct,
        tp_pct,
        entry_price,
      }),
    });
    const data = await res.json();
    if (data.status === 'submitted' || data.status === 'paper') {
      _cmdSetStatus(`✅ ${data.is_paper ? '[PAPER] ' : ''}Ordem enviada! ${data.order_id ? 'ID: ' + data.order_id : ''}`, 'ok');
      _mkPlayTradeSound('win');
      setTimeout(_mkLoadTopBar, 2000);
    } else {
      _cmdSetStatus(`🚫 ${data.reason || data.status || 'Bloqueado'}`, 'error');
    }
  } catch (err) {
    _cmdSetStatus(`❌ Erro: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ============================================================
// SOUND SYSTEM — Web Audio API
// ============================================================
let _soundEnabled = false;
let _audioCtx = null;

function _mkGetAudioCtx() {
  if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  return _audioCtx;
}

function _mkPlayTradeSound(type) {
  if (!_soundEnabled) return;
  try {
    const ctx = _mkGetAudioCtx();
    if (type === 'win') _mkPlayAvengersTheme(ctx);
    else if (type === 'loss') _mkPlayAlarm(ctx);
  } catch (_) {}
}

function _mkPlayAvengersTheme(ctx) {
  // Avengers theme fanfare — simplified 4-note motif
  const notes = [
    { freq: 440.0, dur: 0.12, start: 0.0 },  // A4
    { freq: 523.3, dur: 0.12, start: 0.13 }, // C5
    { freq: 659.3, dur: 0.12, start: 0.26 }, // E5
    { freq: 880.0, dur: 0.35, start: 0.39 }, // A5 (hold)
    { freq: 698.5, dur: 0.12, start: 0.76 }, // F5
    { freq: 880.0, dur: 0.45, start: 0.89 }, // A5 (hold)
  ];
  const now = ctx.currentTime;
  notes.forEach(({ freq, dur, start }) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(freq, now + start);
    gain.gain.setValueAtTime(0, now + start);
    gain.gain.linearRampToValueAtTime(0.18, now + start + 0.02);
    gain.gain.linearRampToValueAtTime(0, now + start + dur);
    osc.start(now + start);
    osc.stop(now + start + dur + 0.01);
  });
}

function _mkPlayAlarm(ctx) {
  const now = ctx.currentTime;
  for (let i = 0; i < 3; i++) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'square';
    osc.frequency.setValueAtTime(880, now + i * 0.25);
    osc.frequency.setValueAtTime(440, now + i * 0.25 + 0.12);
    gain.gain.setValueAtTime(0.15, now + i * 0.25);
    gain.gain.linearRampToValueAtTime(0, now + i * 0.25 + 0.24);
    osc.start(now + i * 0.25);
    osc.stop(now + i * 0.25 + 0.25);
  }
}

function _mkToggleSound() {
  _soundEnabled = !_soundEnabled;
  const btn = document.getElementById('sound-toggle-btn');
  if (btn) {
    btn.textContent = _soundEnabled ? '🔊' : '🔇';
    btn.classList.toggle('active', _soundEnabled);
    btn.title = _soundEnabled ? 'Sons ativados' : 'Sons desativados';
  }
  // Test sound on enable
  if (_soundEnabled) setTimeout(() => _mkPlayTradeSound('win'), 100);
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
  safeBoot(bootMemory,          'bootMemory');
  safeBoot(bootTodaySummary,    'bootTodaySummary');
  safeBoot(bootRiskPanel,       'bootRiskPanel');
  safeBoot(bootEquityCurve,    'bootEquityCurve');
  safeBoot(bootLeaderboard,    'bootLeaderboard');
  // v2 must always run — page isolation, topbar, TradeNow
  _mkBootDashboardV2();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _mkRunAllBoots);
} else {
  _mkRunAllBoots();
}

// ═════════════════════════════════════════════════════════════════════════
// Página de Relatórios
// ═════════════════════════════════════════════════════════════════════════

function _rptFmtPnl(v) {
  const n = parseFloat(v);
  if (isNaN(n)) return '—';
  const sign = n >= 0 ? '+' : '';
  return `<span class="${n >= 0 ? 'ts-green' : 'ts-red'}">${sign}$${Math.abs(n).toFixed(2)}</span>`;
}
function _rptFmtPct(v) {
  const n = parseFloat(v);
  if (isNaN(n)) return '—';
  return `<span class="${n >= 0 ? 'ts-green' : 'ts-red'}">${n >= 0 ? '+' : ''}${n.toFixed(2)}%</span>`;
}

async function loadReports() {
  const days = parseInt(document.getElementById('rpt-days')?.value || '30', 10);
  await Promise.all([
    _rptLoadDaily(days),
    _rptLoadBySymbol(),
    _rptLoadBacktestHistory(),
  ]);
}

async function _rptLoadDaily(days) {
  const tbody = document.getElementById('rpt-daily-body');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" class="rpt-loading">Carregando...</td></tr>';
  try {
    const res = await fetch('/api/pnl/series?days=' + days);
    const d = await res.json();
    const rows = (d.series || d.data || []);

    // Calcular KPIs
    let total = 0, wins = 0, losses = 0, best = -Infinity, worst = Infinity;
    rows.forEach(r => {
      const pnl = parseFloat(r.pnl_usd || r.pnl || 0);
      total += pnl;
      if (pnl > 0) wins++;
      else if (pnl < 0) losses++;
      if (pnl > best) best = pnl;
      if (pnl < worst) worst = pnl;
    });

    const el = id => document.getElementById(id);
    if (el('rpt-kpi-total')) el('rpt-kpi-total').innerHTML = _rptFmtPnl(total);
    if (el('rpt-kpi-wins'))  el('rpt-kpi-wins').textContent = wins + ' dias';
    if (el('rpt-kpi-losses')) el('rpt-kpi-losses').textContent = losses + ' dias';
    if (el('rpt-kpi-best') && isFinite(best))   el('rpt-kpi-best').innerHTML  = _rptFmtPnl(best);
    if (el('rpt-kpi-worst') && isFinite(worst)) el('rpt-kpi-worst').innerHTML = _rptFmtPnl(worst);

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="rpt-loading">Nenhum dado ainda — execute trades para popular o histórico.</td></tr>';
      return;
    }

    tbody.innerHTML = rows.slice().reverse().map(r => {
      const pnl  = parseFloat(r.pnl_usd || r.pnl || 0);
      const pct  = parseFloat(r.pnl_pct || 0);
      const dd   = parseFloat(r.drawdown_pct || 0);
      const date = (r.date_utc || r.date || '').slice(0, 10);
      return `<tr>
        <td>${date}</td>
        <td>${_rptFmtPnl(pnl)}</td>
        <td>${_rptFmtPct(pct)}</td>
        <td>${r.trades_count || 0}</td>
        <td>${r.wins || 0}</td>
        <td class="${dd < 5 ? '' : dd < 15 ? 'ts-red' : 'ts-red'}" style="font-weight:600">${dd.toFixed(2)}%</td>
      </tr>`;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="rpt-loading">Erro: ${err.message}</td></tr>`;
  }
}

async function _rptLoadBySymbol() {
  const tbody = document.getElementById('rpt-symbol-body');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" class="rpt-loading">Carregando...</td></tr>';
  try {
    const res = await fetch('/api/leaderboard?days=90');
    const d = await res.json();
    const rows = (d.rows || d.symbols || d.data || []);
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="rpt-loading">Nenhum dado — execute trades para popular.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => {
      const wr  = parseFloat(r.win_rate || 0);
      const pnl = parseFloat(r.total_pnl_usd || r.pnl_usd || 0);
      const best  = parseFloat(r.best_trade_usd || r.best || 0);
      const worst = parseFloat(r.worst_trade_usd || r.worst || 0);
      const avg   = parseFloat(r.avg_pnl_usd || r.avg || 0);
      return `<tr>
        <td style="font-weight:700">${r.symbol || '—'}</td>
        <td>${r.trade_count || r.count || 0}</td>
        <td class="${wr >= 50 ? 'ts-green' : 'ts-red'}">${wr.toFixed(1)}%</td>
        <td>${_rptFmtPnl(pnl)}</td>
        <td>${_rptFmtPnl(best)}</td>
        <td>${_rptFmtPnl(worst)}</td>
        <td>${_rptFmtPnl(avg)}</td>
      </tr>`;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="rpt-loading">Erro: ${err.message}</td></tr>`;
  }
}

async function _rptLoadBacktestHistory() {
  const grid = document.getElementById('rpt-bt-grid');
  if (!grid) return;
  grid.innerHTML = '<div class="rpt-loading">Carregando...</div>';
  try {
    // Tentar BTC e ETH em paralelo
    const [btcRes, ethRes] = await Promise.all([
      fetch('/api/backtest/history?symbol=BTC').then(r => r.json()).catch(() => ({ ok: false, history: [] })),
      fetch('/api/backtest/history?symbol=ETH').then(r => r.json()).catch(() => ({ ok: false, history: [] })),
    ]);
    const allResults = [
      ...(btcRes.history || []).map(h => ({...h, _sym: 'BTC'})),
      ...(ethRes.history || []).map(h => ({...h, _sym: 'ETH'})),
    ];
    if (!allResults.length) {
      grid.innerHTML = '<div class="rpt-loading">Nenhum backtest executado ainda. Use a página 📊 Backtest para rodar.</div>';
      return;
    }
    grid.innerHTML = allResults.map(h => {
      const ret  = parseFloat(h.total_return_pct || 0);
      const wr   = parseFloat(h.win_rate || h.metrics?.win_rate || 0);
      const sh   = parseFloat(h.sharpe_ratio || h.metrics?.sharpe_ratio || 0);
      const dd   = parseFloat(h.max_drawdown_pct || h.metrics?.max_drawdown_pct || 0);
      const sym  = h.symbol || h._sym || '—';
      const date = (h.generated_at || h.end_date || '').slice(0, 16).replace('T', ' ');
      return `<div class="rpt-bt-card">
        <div class="rpt-bt-sym">${sym}</div>
        <div class="rpt-bt-date">${date}</div>
        <div class="rpt-bt-row"><span>Retorno</span><span class="${ret >= 0 ? 'ts-green' : 'ts-red'}">${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%</span></div>
        <div class="rpt-bt-row"><span>Win Rate</span><span class="${wr >= 50 ? 'ts-green' : 'ts-red'}">${wr.toFixed(1)}%</span></div>
        <div class="rpt-bt-row"><span>Sharpe</span><span>${sh.toFixed(2)}</span></div>
        <div class="rpt-bt-row"><span>Max DD</span><span class="ts-red">${dd.toFixed(2)}%</span></div>
      </div>`;
    }).join('');
  } catch (err) {
    grid.innerHTML = `<div class="rpt-loading">Erro: ${err.message}</div>`;
  }
}

// Export CSV do P&L diário
function _rptExportCsv() {
  const rows = document.querySelectorAll('#rpt-daily-body tr');
  if (!rows.length) return;
  const lines = ['Data,PnL USD,PnL %,Trades,Wins,Drawdown'];
  rows.forEach(tr => {
    const cells = Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim().replace(/[+]/g, ''));
    if (cells.length === 6) lines.push(cells.join(','));
  });
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = 'mekka_pnl_' + new Date().toISOString().slice(0, 10) + '.csv';
  a.click();
  URL.revokeObjectURL(url);
}

// Boot da página de relatórios
let _reportsBooted = false;
function bootReports() {
  if (_reportsBooted) return;
  _reportsBooted = true;
  const daysEl = document.getElementById('rpt-days');
  const refEl  = document.getElementById('rpt-refresh');
  const csvEl  = document.getElementById('rpt-export-csv');
  if (daysEl) daysEl.addEventListener('change', () => loadReports());
  if (refEl)  refEl.addEventListener('click', () => loadReports());
  if (csvEl)  csvEl.addEventListener('click', _rptExportCsv);
  loadReports();
}

// ═════════════════════════════════════════════════════════════════════════
// Today Summary Widget — Overview simplificado para leigos
// ═════════════════════════════════════════════════════════════════════════

let _tsSummaryTimer = null;

function _tsFmt(val) {
  const n = parseFloat(val);
  if (isNaN(n)) return '—';
  const sign = n >= 0 ? '+' : '';
  return sign + n.toFixed(2) + ' USD';
}

function _tsColorClass(val) {
  const n = parseFloat(val);
  if (isNaN(n) || n === 0) return '';
  return n > 0 ? 'ts-green' : 'ts-red';
}

async function loadTodaySummary() {
  try {
    const res = await fetch('/api/today-summary');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const d = await res.json();
    if (!d.ok) throw new Error(d.error || 'API error');

    const hasPrices   = !!d.has_prices;
    const openPnlNull = d.open_pnl_usd === null || d.open_pnl_usd === undefined;

    // ── Paper badge ──────────────────────────────────────────────────────
    const badge = document.getElementById('today-summary-paper-badge');
    if (badge) badge.style.display = d.is_paper ? '' : 'none';

    // ── Aviso sem cotação ────────────────────────────────────────────────
    let noQuoteWarn = document.getElementById('ts-no-quote-warn');
    if (!noQuoteWarn) {
      noQuoteWarn = document.createElement('div');
      noQuoteWarn.id = 'ts-no-quote-warn';
      noQuoteWarn.className = 'ts-warn-banner';
      noQuoteWarn.innerHTML = '⚠️ Sem cotação de mercado — credenciais da Hyperliquid não configuradas. P&L das posições indisponível.';
      const sec = document.getElementById('sec-today-summary');
      if (sec) sec.insertBefore(noQuoteWarn, sec.firstChild);
    }
    noQuoteWarn.style.display = hasPrices ? 'none' : '';

    // ── Big cards ────────────────────────────────────────────────────────
    // Resultado Líquido: se não há preços, mostrar só realizado
    const netEl = document.getElementById('ts-net-val');
    if (netEl) {
      if (openPnlNull) {
        netEl.textContent = _tsFmt(d.daily_pnl_usd);
        netEl.className = 'ts-big-val ' + _tsColorClass(d.daily_pnl_usd);
      } else {
        netEl.textContent = _tsFmt(d.net_pnl_usd);
        netEl.className = 'ts-big-val ' + _tsColorClass(d.net_pnl_usd);
      }
    }
    const subNet = document.getElementById('ts-net-sub');
    if (subNet) subNet.textContent = openPnlNull
      ? (d.day_emoji || '') + ' apenas realizado'
      : (d.day_emoji || '') + ' realizado + aberto';

    const realEl = document.getElementById('ts-realized-val');
    if (realEl) {
      realEl.textContent = _tsFmt(d.daily_pnl_usd);
      realEl.className = 'ts-big-val ' + _tsColorClass(d.daily_pnl_usd);
    }
    const subReal = document.getElementById('ts-realized-sub');
    if (subReal) subReal.textContent = (d.trades_count_today || 0) + ' trade(s) fechado(s) hoje';

    const openEl = document.getElementById('ts-open-val');
    if (openEl) {
      if (openPnlNull) {
        openEl.textContent = '—';
        openEl.className = 'ts-big-val ts-muted';
      } else {
        openEl.textContent = _tsFmt(d.open_pnl_usd);
        openEl.className = 'ts-big-val ' + _tsColorClass(d.open_pnl_usd);
      }
    }
    const subOpen = document.getElementById('ts-open-sub');
    if (subOpen) subOpen.textContent = (d.open_count || 0) + ' posição(ões) ativa(s)'
      + (openPnlNull ? ' · sem cotação' : '');

    // ── Posições abertas ─────────────────────────────────────────────────
    const pgrid  = document.getElementById('ts-positions-grid');
    const pempty = document.getElementById('ts-positions-empty');
    if (pgrid) {
      pgrid.innerHTML = '';
      const items = d.open_positions || [];
      if (pempty) pempty.style.display = items.length ? 'none' : '';
      items.forEach(p => {
        const pnlKnown = p.has_upnl && p.pnl_usd !== null && p.pnl_usd !== undefined;
        const pnlClass = !pnlKnown ? '' : (parseFloat(p.pnl_usd) >= 0 ? 'ts-pos-win' : 'ts-pos-loss');
        const sideLabel = p.side === 'LONG' ? '📈 LONG' : '📉 SHORT';
        const pnlDisplay = pnlKnown
          ? `<span class="ts-pos-pnl ${parseFloat(p.pnl_usd)>=0?'ts-green':'ts-red'}">${_tsFmt(p.pnl_usd)}</span>`
          : `<span class="ts-pos-pnl ts-muted">Aguardando cotação</span>`;
        const markDisplay = p.mark_price
          ? `$${parseFloat(p.mark_price).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})}`
          : '<span class="ts-muted">—</span>';
        pgrid.innerHTML += `
          <div class="ts-pos-card ${pnlClass}">
            <div class="ts-pos-symbol">${p.emoji || '⏳'} ${p.symbol}</div>
            <div class="ts-pos-side">${sideLabel}</div>
            <div class="ts-pos-row"><span class="ts-pos-lbl">Entrada</span><span class="ts-pos-val">$${parseFloat(p.entry_price||0).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})}</span></div>
            <div class="ts-pos-row"><span class="ts-pos-lbl">Preço atual</span><span class="ts-pos-val">${markDisplay}</span></div>
            <div class="ts-pos-row ts-pos-pnl-row"><span class="ts-pos-lbl">Lucro/Prejuízo</span>${pnlDisplay}</div>
          </div>`;
      });
    }

    // ── Trades ───────────────────────────────────────────────────────────
    // Se não há trades de hoje, mostrar recentes com data
    const todayTrades  = d.today_trades  || [];
    const recentTrades = d.recent_trades || [];
    const showRecent   = todayTrades.length === 0 && recentTrades.length > 0;
    const tradesSource = showRecent ? recentTrades : todayTrades;

    const tlist  = document.getElementById('ts-trades-list');
    const tempty = document.getElementById('ts-trades-empty');
    const theader = document.getElementById('ts-trades-header');
    if (theader) theader.textContent = showRecent ? 'Últimos trades (sem trades hoje)' : 'Trades de hoje';

    if (tlist) {
      tlist.innerHTML = '';
      const trades = tradesSource.slice(0, 20);
      if (tempty) tempty.style.display = trades.length ? 'none' : '';
      trades.forEach(t => {
        const pnlKnown = t.pnl_usd !== null && t.pnl_usd !== undefined;
        const pnlClass = pnlKnown ? (t.pnl_usd > 0 ? 'ts-green' : (t.pnl_usd < 0 ? 'ts-red' : '')) : 'ts-muted';
        const pnlText  = pnlKnown ? _tsFmt(t.pnl_usd) : '—';
        let timeStr;
        if (showRecent && t.date) {
          // mostrar data quando não são de hoje
          const d2 = t.date.slice(5);  // MM-DD
          timeStr = d2 + ' ' + (t.timestamp ? t.timestamp.slice(11,16) : '');
        } else {
          timeStr = t.timestamp ? t.timestamp.slice(11,16) : '—';
        }
        tlist.innerHTML += `
          <div class="ts-trade-row">
            <span class="ts-trade-emoji">${t.emoji || '➖'}</span>
            <span class="ts-trade-time">${timeStr}</span>
            <span class="ts-trade-symbol">${t.symbol}</span>
            <span class="ts-trade-side ${t.side === 'BUY' || t.side === 'LONG' ? 'ts-green' : 'ts-red'}">${t.side}</span>
            <span class="ts-trade-status">${t.status}</span>
            <span class="ts-trade-pnl ${pnlClass}">${pnlText}</span>
          </div>`;
      });
    }

    // ── Footer timestamp ─────────────────────────────────────────────────
    const upd = document.getElementById('ts-last-update');
    if (upd) upd.textContent = new Date().toLocaleTimeString('pt-BR');

  } catch (err) {
    console.error('[TodaySummary] erro:', err);
    const upd = document.getElementById('ts-last-update');
    if (upd) upd.textContent = '⚠️ Erro ao carregar';
  }
}

function bootTodaySummary() {
  loadTodaySummary();
  _tsSummaryTimer = _clearTimer(_tsSummaryTimer);
  if (!document.hidden) {
    _tsSummaryTimer = setInterval(loadTodaySummary, 30_000);
  }
}

// ═════════════════════════════════════════════════════════════════════════
// Milestones 36-39 — Backtest Dashboard + Analytics (Stories 224-243)
// ═════════════════════════════════════════════════════════════════════════

// ── Shared helpers ────────────────────────────────────────────────────────
function _btColorVal(val, positiveIsGood = true) {
  if (val === null || val === undefined || val === '—') return '';
  const n = parseFloat(val);
  if (isNaN(n)) return '';
  if (positiveIsGood) return n > 0 ? 'color:#4caf50' : n < 0 ? 'color:#f44336' : '';
  return n < 0 ? 'color:#4caf50' : n > 0 ? 'color:#f44336' : '';
}

function _btFmt(n, decimals = 2, prefix = '') {
  if (n === null || n === undefined) return '—';
  const f = parseFloat(n);
  if (isNaN(f)) return '—';
  const sign = f > 0 ? '+' : '';
  return `${prefix}${sign}${f.toFixed(decimals)}`;
}

// ── Story 225 — Backtest Panel ────────────────────────────────────────────
let _btEquityChart = null;
let _btDrawdownChart = null;

function _btSetStatus(msg, isError = false) {
  const el = document.getElementById('bt-status');
  if (el) { el.textContent = msg; el.style.color = isError ? '#f44336' : ''; }
}

function _btRenderMetrics(data) {
  const m = data.metrics || {};
  const set = (id, val, style) => {
    const el = document.getElementById(id);
    if (el) { el.textContent = val; if (style) el.style = style; }
  };

  const retPct = parseFloat(data.total_return_pct || 0);
  set('bt-val-return', `${retPct >= 0 ? '+' : ''}${retPct.toFixed(2)}%`,
      `font-weight:700;${_btColorVal(retPct)}`);
  set('bt-val-wr',      `${(m.win_rate||0).toFixed(1)}%`);
  set('bt-val-pf',      (m.profit_factor||0).toFixed(3));
  set('bt-val-sharpe',  (m.sharpe_ratio||0).toFixed(3),
      `font-weight:600;${_btColorVal(m.sharpe_ratio)}`);
  set('bt-val-sortino', (m.sortino_ratio||0).toFixed(3));
  set('bt-val-dd',      `-${(m.max_drawdown_pct||0).toFixed(2)}%`,
      'color:#f44336;font-weight:600');
  set('bt-val-trades',  `${m.wins||0}W / ${m.losses||0}L / ${m.total_trades||0}T`);
  set('bt-val-exp',     `$${(m.expectancy_usd||0).toFixed(2)}`);

  // Benchmark
  const bm = data.benchmark;
  const bmRow = document.getElementById('bt-benchmark-row');
  if (bm && bmRow) {
    bmRow.classList.remove('hidden');
    const bmPct = parseFloat(bm.total_return_pct || 0);
    const elBm  = document.getElementById('bt-benchmark-val');
    const elAlpha = document.getElementById('bt-alpha-val');
    if (elBm) { elBm.textContent = `${bmPct >= 0 ? '+' : ''}${bmPct.toFixed(2)}%`; }
    const alpha = retPct - bmPct;
    if (elAlpha) {
      elAlpha.textContent = `(alfa: ${alpha >= 0 ? '+' : ''}${alpha.toFixed(2)}pp)`;
      elAlpha.style.color = alpha >= 0 ? '#4caf50' : '#f44336';
    }
  }
}

function _btRenderEquityCurve(equityCurve) {
  const canvas  = document.getElementById('bt-equity-canvas');
  const canvas2 = document.getElementById('bt-drawdown-canvas');
  if (!canvas || !equityCurve || !equityCurve.length) return;

  const labels   = equityCurve.map(p => p.timestamp ? p.timestamp.slice(0, 10) : '');
  const equities = equityCurve.map(p => p.equity_usd);
  const drawdowns= equityCurve.map(p => -(p.drawdown_pct || 0));

  if (_btEquityChart) { _btEquityChart.destroy(); _btEquityChart = null; }
  if (_btDrawdownChart) { _btDrawdownChart.destroy(); _btDrawdownChart = null; }

  if (typeof Chart === 'undefined') return;

  _btEquityChart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Equity USD',
        data: equities,
        borderColor: '#4caf50',
        backgroundColor: 'rgba(76,175,80,0.1)',
        borderWidth: 2,
        pointRadius: 0,
        fill: true,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxTicksLimit: 8, color: '#aaa' }, grid: { color: '#333' } },
        y: { ticks: { color: '#aaa', callback: v => `$${v.toLocaleString()}` }, grid: { color: '#333' } },
      },
    },
  });

  _btDrawdownChart = new Chart(canvas2.getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Drawdown %',
        data: drawdowns,
        backgroundColor: 'rgba(244,67,54,0.5)',
        borderColor: '#f44336',
        borderWidth: 1,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxTicksLimit: 8, color: '#aaa' }, grid: { color: '#333' } },
        y: { ticks: { color: '#aaa', callback: v => `${v.toFixed(1)}%` }, grid: { color: '#333' } },
      },
    },
  });
}

async function _btRunBacktest() {
  const symbol  = (document.getElementById('bt-symbol')?.value || 'BTC');
  const days    = parseInt(document.getElementById('bt-days')?.value || '30', 10);
  const equity  = parseFloat(document.getElementById('bt-equity')?.value || '10000');
  const btn     = document.getElementById('bt-run-btn');

  if (btn) btn.disabled = true;
  _btSetStatus(`Executando backtest ${symbol} ${days}d...`);

  try {
    const resp = await fetch('/api/backtest/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, days, initial_equity: equity, seed: 42 }),
    });
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || 'Erro desconhecido');

    _btRenderMetrics(data);
    _btRenderEquityCurve(data.equity_curve || []);

    const m = data.metrics || {};
    _btSetStatus(
      `✅ ${symbol} ${days}d — ${m.total_trades||0} trades | WR: ${(m.win_rate||0).toFixed(1)}% | Sharpe: ${(m.sharpe_ratio||0).toFixed(2)}`
    );
  } catch (err) {
    _btSetStatus(`❌ ${err.message}`, true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function _btBootPage() {
  const btn = document.getElementById('bt-run-btn');
  if (btn && !btn._btWired) {
    btn.addEventListener('click', _btRunBacktest);
    btn._btWired = true;
  }
  // C2 fix: usar símbolo selecionado no select em vez de BTC hardcoded
  const _btSymCached = document.getElementById('bt-symbol')?.value || 'BTC';
  fetch('/api/backtest/result?symbol=' + encodeURIComponent(_btSymCached))
    .then(r => r.json())
    .then(d => { if (d.ok) { _btRenderMetrics(d); _btRenderEquityCurve(d.equity_curve||[]); } })
    .catch(() => {});
}

// ── Story 232 — Rolling Performance Panel ────────────────────────────────
async function _rollingRefresh() {
  const symbol = document.getElementById('rolling-symbol')?.value || 'BTC';
  const days   = document.getElementById('rolling-days')?.value || '30';
  const status = document.getElementById('rolling-status');
  const grid   = document.getElementById('rolling-metrics-grid');
  const divBox = document.getElementById('rolling-divergence-box');

  if (status) status.textContent = 'Carregando...';
  try {
    const [rollingResp, divResp] = await Promise.all([
      fetch(`/api/performance/rolling?symbol=${symbol}&days=${days}`).then(r => r.json()),
      fetch(`/api/performance/divergence?symbol=${symbol}`).then(r => r.json()),
    ]);

    if (grid && rollingResp.ok) {
      const r = rollingResp;
      const cards = [
        ['Trades', r.total_trades, '', false],
        ['Win Rate', `${(r.win_rate_pct||0).toFixed(1)}%`, '', true],
        ['Total PnL', `$${(r.total_pnl_usd||0).toFixed(2)}`, _btColorVal(r.total_pnl_usd), true],
        ['Sharpe', (r.sharpe_ratio||0).toFixed(3), _btColorVal(r.sharpe_ratio), true],
        ['Max DD', `-${(r.max_drawdown_pct||0).toFixed(2)}%`, 'color:#f44336', false],
        ['Expectância', `$${(r.expectancy_usd||0).toFixed(2)}`, _btColorVal(r.expectancy_usd), true],
      ];
      // Adicionar comparação com backtest se disponível
      if (r.backtest_sharpe !== undefined) {
        const delta = (r.sharpe_ratio||0) - r.backtest_sharpe;
        cards.push(['Δ Sharpe vs BT', `${delta >= 0 ? '+' : ''}${delta.toFixed(3)}`, _btColorVal(delta), true]);
        cards.push(['BT Win Rate', `${(r.backtest_win_rate||0).toFixed(1)}%`, '', false]);
      }
      grid.innerHTML = cards.map(([label, val, style, _]) =>
        `<div class="bt-metric-card"><span class="bt-metric-label">${label}</span><span class="bt-metric-val" style="${style||''}">${val}</span></div>`
      ).join('');
    }

    if (divBox && divResp.ok) {
      const statusColor = { ok: '#4caf50', warn: '#ff9800', diverging: '#f44336' }[divResp.status] || '#aaa';
      const alertsHtml = (divResp.alerts || []).map(a =>
        `<div class="div-alert div-alert-${(a.severity||'').toLowerCase()}">
          <strong>${a.severity}</strong>: ${a.message}
          <div class="div-rec">${a.recommendation}</div>
        </div>`
      ).join('') || '<div class="muted-line">Sem divergências detectadas ✅</div>';
      divBox.innerHTML = `<div style="color:${statusColor};font-weight:700;margin-bottom:8px">Status: ${(divResp.status||'').toUpperCase()}</div>${alertsHtml}`;
      divBox.classList.remove('hidden');
    }

    if (status) status.textContent = `Atualizado em ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    if (status) { status.textContent = `Erro: ${err.message}`; status.style.color = '#f44336'; }
  }
}

function _rollingBootPage() {
  const btn = document.getElementById('rolling-refresh-btn');
  if (btn && !btn._rollingWired) {
    btn.addEventListener('click', _rollingRefresh);
    btn._rollingWired = true;
  }
  _rollingRefresh();
}

// ── Story 235 — Batman Verdicts Timeline ─────────────────────────────────
let _batmanTlChart = null;

async function _batmanTimelineRefresh() {
  const status = document.getElementById('batman-tl-status');
  const wrap   = document.getElementById('batman-tl-table-wrap');
  if (status) status.textContent = 'Carregando...';
  try {
    const data = await fetch('/api/risk/batman-timeline?limit=100').then(r => r.json());
    if (!data.ok) throw new Error(data.error);

    const tl = data.timeline || [];

    // Chart: APPROVED/REDUCED/REJECTED por dia
    const canvas = document.getElementById('chart-batman-timeline');
    if (canvas && typeof Chart !== 'undefined' && tl.length) {
      const dayMap = {};
      tl.forEach(item => {
        const day = (item.timestamp || '').slice(0, 10) || '—';
        if (!dayMap[day]) dayMap[day] = { APPROVED: 0, REDUCED: 0, REJECTED: 0 };
        const v = (item.verdict || '').toUpperCase();
        if (v.includes('APPROV')) dayMap[day].APPROVED++;
        else if (v.includes('REDUC')) dayMap[day].REDUCED++;
        else if (v.includes('REJECT')) dayMap[day].REJECTED++;
      });
      const days   = Object.keys(dayMap).sort();
      if (_batmanTlChart) { _batmanTlChart.destroy(); _batmanTlChart = null; }
      _batmanTlChart = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
          labels: days,
          datasets: [
            { label: 'Approved', data: days.map(d => dayMap[d].APPROVED), backgroundColor: 'rgba(76,175,80,0.7)' },
            { label: 'Reduced',  data: days.map(d => dayMap[d].REDUCED),  backgroundColor: 'rgba(255,152,0,0.7)' },
            { label: 'Rejected', data: days.map(d => dayMap[d].REJECTED), backgroundColor: 'rgba(244,67,54,0.7)' },
          ],
        },
        options: {
          responsive: true,
          plugins: { legend: { labels: { color: '#ccc' } } },
          scales: {
            x: { stacked: true, ticks: { color: '#aaa', maxTicksLimit: 10 }, grid: { color: '#333' } },
            y: { stacked: true, ticks: { color: '#aaa' }, grid: { color: '#333' } },
          },
        },
      });
    }

    // Tabela últimos 20
    if (wrap) {
      const rows = tl.slice(-20).reverse().map(item => {
        const v = (item.verdict || '').toUpperCase();
        const color = v.includes('APPROV') ? '#4caf50' : v.includes('REDUC') ? '#ff9800' : '#f44336';
        return `<tr>
          <td>${(item.timestamp||'').slice(0,16).replace('T',' ')}</td>
          <td>${item.symbol||'—'}</td>
          <td style="color:${color};font-weight:700">${item.verdict||'—'}</td>
          <td>${item.reason||'—'}</td>
        </tr>`;
      }).join('');
      wrap.innerHTML = `<table class="compare-table"><thead><tr><th>Timestamp</th><th>Símbolo</th><th>Verdict</th><th>Razão</th></tr></thead><tbody>${rows}</tbody></table>`;
    }

    if (status) status.textContent = `${tl.length} registros`;
  } catch (err) {
    if (status) { status.textContent = `Erro: ${err.message}`; status.style.color = '#f44336'; }
  }
}

function _batmanTimelineBootPage() {
  const btn = document.getElementById('batman-tl-refresh');
  if (btn && !btn._btlWired) {
    btn.addEventListener('click', _batmanTimelineRefresh);
    btn._btlWired = true;
  }
  _batmanTimelineRefresh();
}

// ── Story 238 — Concentration Heatmap ────────────────────────────────────
let _concChart = null;

async function _concentrationRefresh() {
  const status = document.getElementById('conc-status');
  if (status) status.textContent = 'Carregando...';
  try {
    const data = await fetch('/api/risk/concentration').then(r => r.json());
    if (!data.ok) throw new Error(data.error);

    const conc   = data.concentration || [];
    const canvas = document.getElementById('chart-concentration');
    if (canvas && conc.length && typeof Chart !== 'undefined') {
      const labels = conc.map(c => c.symbol);
      const pcts   = conc.map(c => c.concentration_pct);
      const colors = conc.map(c =>
        c.concentration_pct > 50 ? 'rgba(244,67,54,0.8)'
        : c.concentration_pct > 30 ? 'rgba(255,152,0,0.8)'
        : 'rgba(76,175,80,0.8)'
      );

      if (_concChart) { _concChart.destroy(); _concChart = null; }
      _concChart = new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
        data: {
          labels,
          datasets: [{ data: pcts, backgroundColor: colors, borderColor: '#1e1e2e', borderWidth: 2 }],
        },
        options: {
          responsive: true,
          plugins: {
            legend: { position: 'right', labels: { color: '#ccc' } },
            tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.parsed.toFixed(1)}%` } },
          },
        },
      });
    }

    const totalUsd = (data.total_notional_usd || 0).toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
    if (status) status.textContent = `Total: ${totalUsd} | ${data.symbol_count||0} símbolos`;
  } catch (err) {
    if (status) { status.textContent = `Erro: ${err.message}`; status.style.color = '#f44336'; }
  }
}

function _concentrationBootPage() {
  const btn = document.getElementById('conc-refresh-btn');
  if (btn && !btn._concWired) {
    btn.addEventListener('click', _concentrationRefresh);
    btn._concWired = true;
  }
  _concentrationRefresh();
}

// ── Story 239-242 — Multiagent Debate Panel ───────────────────────────────
async function _debateRun() {
  const symbol = document.getElementById('debate-symbol')?.value || 'BTC';
  const rounds = parseInt(document.getElementById('debate-rounds')?.value || '2', 10);
  const btn    = document.getElementById('debate-run-btn');
  const status = document.getElementById('debate-status');
  const vbox   = document.getElementById('debate-verdict-box');
  const tWrap  = document.getElementById('debate-votes-table-wrap');

  if (btn) btn.disabled = true;
  if (status) status.textContent = `Executando debate ${symbol} (${rounds} rodadas)...`;
  if (vbox) vbox.classList.add('hidden');

  try {
    const data = await fetch('/api/debate/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, rounds }),
    }).then(r => r.json());

    if (!data.ok) throw new Error(data.error);

    // Exibir verdict
    if (vbox) {
      const actionEl = document.getElementById('debate-consensus-action');
      const confEl   = document.getElementById('debate-consensus-conf');
      const notesEl  = document.getElementById('debate-notes');
      const actionColor = data.consensus_action === 'LONG' ? '#4caf50'
        : data.consensus_action === 'SHORT' ? '#f44336' : '#aaa';
      if (actionEl) { actionEl.textContent = data.consensus_action || '—'; actionEl.style.background = actionColor; }
      if (confEl)   { confEl.textContent   = `${((data.consensus_confidence||0)*100).toFixed(0)}% confiança`; }
      if (notesEl)  { notesEl.innerHTML = (data.notes||[]).map(n => `<div class="debate-note">⚠️ ${n}</div>`).join('') || ''; }
      vbox.classList.remove('hidden');
    }

    // Tabela de votos
    if (tWrap && data.vote_table) {
      const rows = data.vote_table.map(v => {
        const color = v.action === 'LONG' ? '#4caf50' : v.action === 'SHORT' ? '#f44336' : '#aaa';
        return `<tr>
          <td>${v.agent}</td>
          <td style="color:${color};font-weight:700">${v.action}</td>
          <td>${((v.confidence||0)*100).toFixed(0)}%</td>
          <td>R${v.round}</td>
          <td>${v.reasoning||'—'}</td>
        </tr>`;
      }).join('');
      tWrap.innerHTML = `<table class="compare-table"><thead><tr><th>Agente</th><th>Voto</th><th>Conf.</th><th>Rodada</th><th>Raciocínio</th></tr></thead><tbody>${rows}</tbody></table>`;
    }

    const dissenters = (data.dissent_agents||[]).join(', ') || 'Nenhum';
    if (status) status.textContent = `✅ Consenso: ${data.consensus_action} | Dissidentes: ${dissenters} | ${data.total_votes} votos`;

    // Recarregar histórico
    _debateLoadHistory(symbol);
  } catch (err) {
    if (status) { status.textContent = `❌ ${err.message}`; status.style.color = '#f44336'; }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function _debateLoadHistory(symbol) {
  const wrap = document.getElementById('debate-history-list');
  if (!wrap) return;
  try {
    const data = await fetch(`/api/debate/history?symbol=${symbol}&limit=10`).then(r => r.json());
    if (!data.ok || !data.history.length) {
      wrap.innerHTML = '<div class="muted-line">Sem histórico ainda.</div>';
      return;
    }
    wrap.innerHTML = data.history.map(item => {
      const color = item.consensus_action === 'LONG' ? '#4caf50'
        : item.consensus_action === 'SHORT' ? '#f44336' : '#aaa';
      return `<div class="debate-history-item">
        <span class="muted-line">${(item.timestamp||'').slice(0,16).replace('T',' ')}</span>
        <span style="color:${color};font-weight:700;margin-left:8px">${item.consensus_action||'—'}</span>
        <span class="muted-line" style="margin-left:4px">${((item.consensus_confidence||0)*100).toFixed(0)}%</span>
        <span class="muted-line" style="margin-left:8px">${item.total_votes||0} votos</span>
      </div>`;
    }).join('');
  } catch (_) {}
}

function _debateBootPage() {
  const btn = document.getElementById('debate-run-btn');
  if (btn && !btn._debateWired) {
    btn.addEventListener('click', _debateRun);
    btn._debateWired = true;
  }
  const sym = document.getElementById('debate-symbol')?.value || 'BTC';
  _debateLoadHistory(sym);
}

// ── Boot analytics & backtest pages on first visit ───────────────────────
// H2 fix: flags para evitar duplo boot ao clicar múltiplas vezes na nav
let _btPageBooted = false;
let _analyticsPageBooted = false;

(function _bootNewPages() {
  // Hook into page navigation to lazy-boot new pages
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.page-nav-btn');
    if (!btn) return;
    const page = btn.dataset.page;
    if (page === 'reports') setTimeout(bootReports, 50);
    if (page === 'backtest' && !_btPageBooted) {
      _btPageBooted = true;
      setTimeout(_btBootPage, 50);
    }
    if (page === 'analytics' && !_analyticsPageBooted) {
      _analyticsPageBooted = true;
      setTimeout(_rollingBootPage, 50);
      setTimeout(_batmanTimelineBootPage, 100);
      setTimeout(_concentrationBootPage, 150);
      setTimeout(_debateBootPage, 200);
    }
    // Clicar de novo na mesma página atualiza os dados sem re-registrar listeners
    if (page === 'backtest' && _btPageBooted) setTimeout(() => { try { _btRenderPage && _btRenderPage(); } catch(_){} }, 50);
    if (page === 'analytics' && _analyticsPageBooted) {
      setTimeout(_rollingRefresh, 50);
      setTimeout(_batmanTimelineRefresh, 100);
      setTimeout(_concentrationRefresh, 150);
      setTimeout(_debateLoadHistory, 200);
    }
  });

  // Also boot if already on these pages on load
  const current = (() => { try { return localStorage.getItem('mekka_current_page'); } catch (_) { return null; } })();
  if (current === 'backtest' && !_btPageBooted) {
    _btPageBooted = true;
    setTimeout(_btBootPage, 300);
  }
  if (current === 'analytics' && !_analyticsPageBooted) {
    _analyticsPageBooted = true;
    setTimeout(_rollingBootPage, 300);
    setTimeout(_batmanTimelineBootPage, 350);
    setTimeout(_concentrationBootPage, 400);
    setTimeout(_debateBootPage, 450);
  }
})();
