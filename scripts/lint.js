const fs = require('node:fs');
const path = require('node:path');

const root = process.cwd();
const allowedExt = new Set(['.ts', '.md', '.json']);
const forbidden = [/from\s+['\"].*whatsapp.*['\"]/i, /require\(['\"].*whatsapp.*['\"]\)/i, /twilio/i];
const ignored = new Set(['node_modules', 'dist', '.git', 'aiox-core']);
const allowedRoots = [
  'agents',
  'backtesting',
  'cli',
  'docs',
  'exchanges',
  'execution-engine',
  'market-data',
  'memory',
  'observability',
  'prompts',
  'risk-engine',
  'scripts',
  'squads',
  'strategy-engine',
  'tests',
  'workflows',
  'README.md',
  'AGENTS.md',
  'package.json',
  'tsconfig.json',
  'index.ts',
];

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (ignored.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else out.push(full);
  }
  return out;
}

const scopedPaths = [];
for (const item of allowedRoots) {
  const full = path.join(root, item);
  if (fs.existsSync(full)) {
    const stat = fs.statSync(full);
    if (stat.isDirectory()) scopedPaths.push(...walk(full));
    else scopedPaths.push(full);
  }
}

const files = scopedPaths.filter((f) => allowedExt.has(path.extname(f)));
const violations = [];
for (const file of files) {
  if (file.includes(`${path.sep}squads${path.sep}`)) {
    continue;
  }

  const content = fs.readFileSync(file, 'utf8');
  for (const rule of forbidden) {
    if (rule.test(content)) {
      violations.push(`${path.relative(root, file)} violates isolation rule: ${rule}`);
    }
  }
}

if (violations.length > 0) {
  console.error('Lint failed with isolation violations:');
  for (const v of violations) console.error(`- ${v}`);
  process.exit(1);
}

console.log(`Lint passed: scanned ${files.length} files.`);
