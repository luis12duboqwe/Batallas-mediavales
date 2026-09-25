import { readdir, readFile, stat } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const DIST_DIR = fileURLToPath(new URL('../dist/', import.meta.url));
const MAX_INITIAL_JS_BYTES = 500 * 1024;
const MAX_SINGLE_CHUNK_BYTES = 400 * 1024;

const formatKiB = (bytes) => `${(bytes / 1024).toFixed(1)} KiB`;

async function listJavaScriptFiles(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await listJavaScriptFiles(path));
    else if (entry.name.endsWith('.js')) files.push(path);
  }
  return files;
}

const html = await readFile(join(DIST_DIR, 'index.html'), 'utf8');
const initialAssetNames = new Set();
for (const match of html.matchAll(/<script\b[^>]*\bsrc=["']([^"']+\.js)["'][^>]*>/gi)) initialAssetNames.add(match[1]);
for (const match of html.matchAll(/<link\b[^>]*\brel=["']modulepreload["'][^>]*\bhref=["']([^"']+\.js)["'][^>]*>/gi)) initialAssetNames.add(match[1]);

if (initialAssetNames.size === 0) throw new Error('Performance budget: no initial JavaScript assets found in dist/index.html');

let initialBytes = 0;
for (const assetName of initialAssetNames) {
  const relativePath = assetName.replace(/^\//, '');
  initialBytes += (await stat(join(DIST_DIR, relativePath))).size;
}

const jsFiles = await listJavaScriptFiles(join(DIST_DIR, 'assets'));
let largest = { path: '', size: 0 };
for (const path of jsFiles) {
  const size = (await stat(path)).size;
  if (size > largest.size) largest = { path, size };
}

const failures = [];
if (initialBytes > MAX_INITIAL_JS_BYTES) {
  failures.push(`initial JS ${formatKiB(initialBytes)} exceeds ${formatKiB(MAX_INITIAL_JS_BYTES)}`);
}
if (largest.size > MAX_SINGLE_CHUNK_BYTES) {
  failures.push(`largest JS chunk ${formatKiB(largest.size)} exceeds ${formatKiB(MAX_SINGLE_CHUNK_BYTES)}`);
}

if (failures.length) {
  console.error(`Performance budget failed:\n- ${failures.join('\n- ')}`);
  process.exit(1);
}

console.log(`Performance budget passed: initial JS ${formatKiB(initialBytes)}, largest chunk ${formatKiB(largest.size)}, ${jsFiles.length} JS chunks`);
