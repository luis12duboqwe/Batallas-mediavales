import { readdir, readFile, stat } from 'node:fs/promises';
import { extname, join } from 'node:path';

const DIST = new URL('../dist/', import.meta.url);
const KiB = 1024;
const budgets = {
  entryJs: 500 * KiB,
  anyJs: 500 * KiB,
  css: 120 * KiB,
  audioTotal: 0,
};

const files = [];
async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await walk(path);
    else files.push({ path, size: (await stat(path)).size });
  }
}

await walk(DIST.pathname);
const html = await readFile(new URL('../dist/index.html', import.meta.url), 'utf8');
const entryMatch = html.match(/<script[^>]+src="([^"]+\.js)"[^>]*>/i);
if (!entryMatch) throw new Error('Performance budget: unable to identify Vite entry JS from dist/index.html');

const entryName = entryMatch[1].split('/').pop();
const entryFile = files.find((file) => file.path.endsWith(`/${entryName}`));
if (!entryFile) throw new Error(`Performance budget: entry asset ${entryName} not found`);

const jsFiles = files.filter((file) => extname(file.path) === '.js');
const cssFiles = files.filter((file) => extname(file.path) === '.css');
const audioFiles = files.filter((file) => ['.mp3', '.wav', '.ogg', '.m4a', '.aac'].includes(extname(file.path).toLowerCase()));
const violations = [];

if (entryFile.size > budgets.entryJs) violations.push(`entry JS ${entryName} is ${(entryFile.size / KiB).toFixed(1)} KiB > 500 KiB`);
for (const file of jsFiles) {
  if (file.size > budgets.anyJs) violations.push(`JS chunk ${file.path.split('/').pop()} is ${(file.size / KiB).toFixed(1)} KiB > 500 KiB`);
}
for (const file of cssFiles) {
  if (file.size > budgets.css) violations.push(`CSS ${file.path.split('/').pop()} is ${(file.size / KiB).toFixed(1)} KiB > 120 KiB`);
}
const audioTotal = audioFiles.reduce((sum, file) => sum + file.size, 0);
if (audioTotal > budgets.audioTotal) violations.push(`built audio assets total ${(audioTotal / KiB).toFixed(1)} KiB; BM-0082 requires procedural audio with 0 binary audio assets`);

const largestJs = [...jsFiles].sort((a, b) => b.size - a.size)[0];
console.log(`Performance budget: entry ${(entryFile.size / KiB).toFixed(1)} KiB; largest JS ${largestJs ? (largestJs.size / KiB).toFixed(1) : '0.0'} KiB; CSS ${cssFiles.reduce((sum, file) => sum + file.size, 0) / KiB} KiB; audio ${(audioTotal / KiB).toFixed(1)} KiB`);
if (violations.length) {
  console.error('Performance budget failed:\n' + violations.join('\n'));
  process.exit(1);
}
console.log('Performance budget passed');
