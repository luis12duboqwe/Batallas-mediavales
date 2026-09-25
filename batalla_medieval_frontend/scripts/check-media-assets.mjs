import { access, readdir, readFile } from 'node:fs/promises';
import { extname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  BINARY_AUDIO_EXTENSIONS,
  containsBinaryAudioReference,
  hasBinaryAudioExtension,
} from './media-policy.mjs';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const INPUT_ROOTS = [join(ROOT, 'src'), join(ROOT, 'public')];
const ROOT_TEXT_FILES = [join(ROOT, 'index.html')];
const TEXT_EXTENSIONS = new Set(['.js', '.jsx', '.css', '.html', '.json', '.svg']);
const failures = [];

// Keep the detector itself under regression coverage. Template literals are a
// common way to construct Audio/fetch URLs and must not bypass the policy.
const templateLiteralProbe = 'new Audio(`https://example.invalid/probe.opus`)';
if (!containsBinaryAudioReference(templateLiteralProbe)) {
  failures.push('media-policy self-check: template-literal binary audio reference was not detected');
}

async function exists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function inspectFile(path) {
  const display = relative(ROOT, path);
  if (hasBinaryAudioExtension(path)) {
    failures.push(`${display}: binary audio asset is not approved; use project-owned procedural Web Audio or document an explicit reviewed exception`);
    return;
  }

  if (!TEXT_EXTENSIONS.has(extname(path).toLowerCase())) return;
  const source = await readFile(path, 'utf8');
  if (containsBinaryAudioReference(source)) {
    failures.push(`${display}: direct binary audio reference is not approved`);
  }
}

async function walk(directory) {
  if (!await exists(directory)) return;
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await walk(path);
    else await inspectFile(path);
  }
}

for (const directory of INPUT_ROOTS) await walk(directory);
for (const path of ROOT_TEXT_FILES) if (await exists(path)) await inspectFile(path);

if (failures.length) {
  console.error('BM-0082 media asset policy failed:');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log(`BM-0082 media asset policy passed: no binary audio assets/references (${BINARY_AUDIO_EXTENSIONS.length} blocked extensions) in src, public or index.html`);
