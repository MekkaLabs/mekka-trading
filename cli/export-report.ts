import { MegazordRuntime } from '../workflows/megazord-runtime';

const missionId = process.argv[2];
if (!missionId) {
  console.error('Usage: node dist/cli/export-report.js <mission-id>');
  process.exit(1);
}

const runtime = new MegazordRuntime();
const outputPath = runtime.exportMissionReport(missionId);
console.log(JSON.stringify({ missionId, outputPath }));
