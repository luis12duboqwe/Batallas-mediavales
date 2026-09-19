import { readdir, readFile } from 'node:fs/promises';
import { extname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const sourceRoot = join(root, 'src');
const checkedExtensions = new Set(['.js', '.jsx', '.css', '.html', '.json', '.svg']);
const pictographicEmoji = /\p{Extended_Pictographic}/gu;

const remoteMediaPatterns = [
  /@import\s+url\(\s*['"]?(?:https?:)?\/\//i,
  /url\(\s*['"]?(?:https?:)?\/\//i,
  /<(?:img|audio|video|source)\b[^>]*\bsrc\s*=\s*['"](?:https?:)?\/\//i,
  /<(?:image|use)\b[^>]*\b(?:href|xlink:href)\s*=\s*['"](?:https?:)?\/\//i,
];

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(path));
    else if (checkedExtensions.has(extname(entry.name))) files.push(path);
  }
  return files;
}

const files = [...await walk(sourceRoot), join(root, 'index.html')];
const failures = [];
for (const path of files) {
  const text = await readFile(path, 'utf8');
  const display = relative(root, path);
  const emojiMatches = [...new Set(text.match(pictographicEmoji) || [])];
  for (const emoji of emojiMatches) {
    failures.push(`${display}: pictographic emoji is not approved production iconography (${emoji})`);
  }
  for (const pattern of remoteMediaPatterns) {
    if (pattern.test(text)) failures.push(`${display}: remote runtime visual/media dependency (${pattern})`);
  }
}

if (failures.length) {
  console.error('BM-0080 visual asset policy failed:');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}
console.log(`BM-0080 visual asset policy passed (${files.length} frontend source files checked)`);
