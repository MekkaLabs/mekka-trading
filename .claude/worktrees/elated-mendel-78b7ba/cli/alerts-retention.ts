import { AlertsRetentionManager } from '../observability/alerts/retention-manager';

const manager = new AlertsRetentionManager();
const report = manager.enforce();
console.log(JSON.stringify(report));
