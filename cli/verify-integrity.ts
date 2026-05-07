import { MegazordRuntime } from '../workflows/megazord-runtime';

const missionId = process.argv[2];
if (!missionId) {
  console.error('Usage: node dist/cli/verify-integrity.js <mission-id>');
  process.exit(1);
}

const runtime = new MegazordRuntime();
const integrity = runtime.verifyMissionIntegrity(missionId);
console.log(JSON.stringify(integrity));
if (!integrity.events.valid || !integrity.audits.valid) {
  process.exit(2);
}
