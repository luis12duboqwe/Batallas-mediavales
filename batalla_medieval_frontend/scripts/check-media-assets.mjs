import { readdir, readFile } from 'node:fs/promises';
import { extname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const SOURCE_ROOT = join(ROOT, 'src');
const BINARY_AUDIO_EXTENSIONS = new Set(['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac']);
const TEXT_EXTENSIONS = new Set(['.js', '.jsx', '.css', '.html', '.json', '.svg']);
const AUDIO_REFERENCE = /\.(?:mp3|wav|ogg|m4a|aac|flac)(?:[?#'"`)\s]|$)/i;
const failures = [];

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      await walk(path);
      continue;
    }

    const extension = extname(entry.name).toLowerCase();
    const display = relative(ROOT, path);
    if (BINARY_AUDIO_EXTENSIONS.has(extension)) {
      failures.push(`${display}: binary audio asset is not approved; use project-owned procedural Web Audio or document an explicit reviewed exception`);
      continue;
    }

    if (!TEXT_EXTENSIONS.has(extension)) continue;
    const source = await readFile(path, 'utf8');
    if (AUDIO_REFERENCE.test(source)) {
      failures.push(`${display}: direct binary audio reference is not approved`);
    }
  }
}

await walk(SOURCE_ROOT);

if (failures.length) {
  console.error('BM-0082 media asset policy failed:');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log('BM-0082 media asset policy passed: no binary audio assets or direct binary-audio references found in src');
