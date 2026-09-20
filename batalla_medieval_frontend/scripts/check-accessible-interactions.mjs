import { readdir, readFile } from 'node:fs/promises';
import { extname, join, relative } from 'node:path';

const ROOT = new URL('../src/', import.meta.url);
const GENERIC_CLICK_TARGET = /<(div|span|li)\b[^>]*\bonClick\s*=/gms;
const SOURCE_EXTENSIONS = new Set(['.js', '.jsx']);
const violations = [];

async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      await walk(path);
      continue;
    }
    if (!SOURCE_EXTENSIONS.has(extname(entry.name))) continue;

    const source = await readFile(path, 'utf8');
    for (const match of source.matchAll(GENERIC_CLICK_TARGET)) {
      const line = source.slice(0, match.index).split('\n').length;
      violations.push(`${relative(ROOT.pathname, path)}:${line} <${match[1]}> uses onClick; use a native interactive element or documented keyboard semantics`);
    }
  }
}

await walk(ROOT.pathname);

if (violations.length) {
  console.error('Accessibility interaction policy failed:\n' + violations.join('\n'));
  process.exit(1);
}

console.log('Accessibility interaction policy passed: no click-only generic div/span/li controls found');
