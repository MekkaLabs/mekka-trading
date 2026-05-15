import { OpsStatusCollector } from '../observability/ops-status';

const collector = new OpsStatusCollector();
const trendWindow = Number(process.env.MEKKA_OPS_TREND_WINDOW);
const lockThreshold = Number(process.env.MEKKA_OPS_LOCK_CONTENTION_THRESHOLD);
const replayFailureWarn = Number(process.env.MEKKA_OPS_REPLAY_FAILURE_WARN);
const replayFailureCritical = Number(process.env.MEKKA_OPS_REPLAY_FAILURE_CRITICAL);
const suppressionWindow = Number(process.env.MEKKA_OPS_ALERT_SUPPRESSION_MINUTES);
const marketRegimeRaw = process.env.MEKKA_OPS_MARKET_REGIME;
const marketRegime =
  marketRegimeRaw === 'normal' || marketRegimeRaw === 'elevated' || marketRegimeRaw === 'critical'
    ? marketRegimeRaw
    : undefined;

const report = collector.collect({
  trendWindow: Number.isFinite(trendWindow) && trendWindow > 0 ? trendWindow : undefined,
  lockContentionThreshold: Number.isFinite(lockThreshold) && lockThreshold > 0 ? lockThreshold : undefined,
  replayFailureRateWarn: Number.isFinite(replayFailureWarn) ? replayFailureWarn : undefined,
  replayFailureRateCritical: Number.isFinite(replayFailureCritical) ? replayFailureCritical : undefined,
  alertSuppressionWindowMinutes: Number.isFinite(suppressionWindow) ? suppressionWindow : undefined,
  marketRegime,
});
const outputPath = collector.exportLatest(report);

console.log(
  JSON.stringify({
    report,
    outputPath,
  }),
);

if (report.alerts.some((a) => a.severity === 'critical')) {
  process.exit(2);
}
