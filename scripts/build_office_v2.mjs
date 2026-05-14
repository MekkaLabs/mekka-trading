// Build the Office v2 React app into a single minified bundle so the
// browser doesn't have to ship Babel-standalone (~700KB) on every load.
//
// Usage:
//   npm run build:office-v2
//
// The bundle is written next to the source files. The HTML decides at
// load time whether to use the bundle (if present) or fall back to
// Babel-standalone for live-edit dev workflows.

import esbuild from 'esbuild';
import { existsSync } from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const sourceDir = path.join(root, 'src/dashboard/static/office_v2');
const entry = path.join(sourceDir, 'mount.js');
const outfile = path.join(sourceDir, 'office_v2.bundle.js');

if (!existsSync(entry)) {
  console.error(`[build:office-v2] missing entry: ${entry}`);
  process.exit(1);
}

await esbuild.build({
  entryPoints: [entry],
  bundle: true,
  format: 'iife',
  target: 'es2020',
  platform: 'browser',
  sourcemap: false,
  minify: true,
  outfile,
  loader: { '.js': 'jsx', '.jsx': 'jsx', '.css': 'css' },
  // Sources use top-level locals + `window.X = ...` instead of ES exports,
  // so we transform JSX without wrapping each file as a module — esbuild's
  // `iife` format with `bundle: true` handles ordering through mount.js.
  jsx: 'transform',
  legalComments: 'none',
  define: {
    'process.env.NODE_ENV': '"production"',
  },
});

console.log(`[build:office-v2] wrote ${path.relative(root, outfile)}`);
