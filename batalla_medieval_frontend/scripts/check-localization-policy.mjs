import { readdir, readFile } from 'node:fs/promises';
import { extname, join, relative } from 'node:path';

const SRC_ROOT = new URL('../src/', import.meta.url);
const SOURCE_EXTENSIONS = new Set(['.js', '.jsx', '.json']);
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
    const displayPath = relative(SRC_ROOT.pathname, path);

    if (displayPath !== 'locales/en.json' && /locales\/en\.json/.test(source)) {
      violations.push(`${displayPath}: imports the retired English production locale`);
    }
    if (/value\s*=\s*["']en["']/.test(source)) {
      violations.push(`${displayPath}: exposes English as a selectable production value`);
    }
    if (/<select\b[^>]*\bname\s*=\s*["']language["']/ms.test(source)) {
      violations.push(`${displayPath}: exposes a runtime language selector`);
    }
  }
}

await walk(SRC_ROOT.pathname);

const i18nSource = await readFile(new URL('../src/i18n.js', import.meta.url), 'utf8');
if (!/supportedLngs:\s*\[\s*['"]es['"]\s*\]/.test(i18nSource)) {
  violations.push('i18n.js: production runtime must explicitly support Spanish only');
}
if (!/lng:\s*['"]es['"]/.test(i18nSource) || !/fallbackLng:\s*['"]es['"]/.test(i18nSource)) {
  violations.push('i18n.js: language and fallback must both be Spanish');
}

if (violations.length) {
  console.error('Localization policy failed:\n' + violations.join('\n'));
  process.exit(1);
}

console.log('Localization policy passed: Spanish is the only selectable/imported production locale');
