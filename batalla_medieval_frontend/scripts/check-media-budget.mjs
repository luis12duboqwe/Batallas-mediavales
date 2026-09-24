import { readdir, readFile, stat } from 'node:fs/promises';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const SRC = join(ROOT, 'src');
const SRC_ASSETS = join(SRC, 'assets');
const DIST_ASSETS = join(ROOT, 'dist', 'assets');
const AUDIO_EXTENSIONS = new Set(['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.opus']);
const MAX_JS_CHUNK_BYTES = 700_000;
const MAX_CSS_CHUNK_BYTES = 70_000;
const violations = [];

async function walk(directory) {
  let entries;
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch (error) {
    if (error.code === 'ENOENT') return [];
    throw error;
  }

  const files = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(path));
    else files.push(path);
  }
  return files;
}

const sourceAssets = await walk(SRC_ASSETS);
for (const path of sourceAssets) {
  if (AUDIO_EXTENSIONS.has(extname(path).toLowerCase())) {
    violations.push(`Binary audio is not allowed after BM-0082: ${path.slice(ROOT.length + 1)}`);
  }
}

const sourceFiles = (await walk(SRC)).filter((path) => ['.js', '.jsx', '.css'].includes(extname(path)));
const audioReference = /\.(?:mp3|wav|ogg|m4a|aac|flac|opus)(?:[?"'`)]|$)/i;
for (const path of sourceFiles) {
  const content = await readFile(path, 'utf8');
  if (audioReference.test(content)) {
    violations.push(`Source references a binary audio asset: ${path.slice(ROOT.length + 1)}`);
  }
}

const distFiles = await walk(DIST_ASSETS);
if (distFiles.length === 0) violations.push('dist/assets is missing; run the media budget after vite build');

let largestJs = { path: '', size: 0 };
let largestCss = { path: '', size: 0 };
for (const path of distFiles) {
  const extension = extname(path).toLowerCase();
  const { size } = await stat(path);
  if (AUDIO_EXTENSIONS.has(extension)) violations.push(`Built output contains binary audio: ${path.slice(ROOT.length + 1)}`);
  if (extension === '.js' && size > largestJs.size) largestJs = { path, size };
  if (extension === '.css' && size > largestCss.size) largestCss = { path, size };
}

if (!largestJs.path) violations.push('No JavaScript chunk found in dist/assets');
if (!largestCss.path) violations.push('No CSS chunk found in dist/assets');
if (largestJs.size > MAX_JS_CHUNK_BYTES) {
  violations.push(`Largest JS chunk ${largestJs.size} B exceeds ${MAX_JS_CHUNK_BYTES} B budget`);
}
if (largestCss.size > MAX_CSS_CHUNK_BYTES) {
  violations.push(`Largest CSS chunk ${largestCss.size} B exceeds ${MAX_CSS_CHUNK_BYTES} B budget`);
}

if (violations.length) {
  console.error('BM-0082 media/performance budget failed:\n' + violations.join('\n'));
  process.exit(1);
}

console.log(`BM-0082 media budget passed: no binary audio; max JS ${largestJs.size} B; max CSS ${largestCss.size} B`);
