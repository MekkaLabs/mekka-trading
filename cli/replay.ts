import { MegazordRuntime } from '../workflows/megazord-runtime';

const missionId = process.argv[2];
if (!missionId) {
  console.error('Usage: node dist/cli/replay.js <mission-id>');
  process.exit(1);
}

const runtime = new MegazordRuntime();
const report = runtime.replayMission(missionId);
console.log(JSON.stringify(report));
