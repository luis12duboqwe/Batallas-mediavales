import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// A full snapshot subscription rerenders every city screen on the 1 Hz
// resource tick, even when that screen only uses currentCity or an action.
const srcDirectory = fileURLToPath(new URL('../src/', import.meta.url));
const violations = [];

async function scan(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      await scan(path);
      continue;
    }
    if (!/\.(jsx?|tsx?)$/.test(entry.name)) continue;
    const source = await readFile(path, 'utf8');
    if (/\buseCityStore\s*\(\s*\)/.test(source)) violations.push(path);
  }
}

await scan(srcDirectory);
if (violations.length) {
  console.error('Full city store subscriptions cause resource tick rerenders:\n' + violations.join('\n'));
  process.exitCode = 1;
} else {
  console.log('BM-0085 selective city subscriptions passed: no full store subscribers in src');
}
