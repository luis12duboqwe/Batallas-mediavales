import { access, readdir, readFile } from 'node:fs/promises';
import { extname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const SRC = join(ROOT, 'src');
const ES_CATALOG = join(SRC, 'locales', 'es.json');
const EN_CATALOG = join(SRC, 'locales', 'en.json');
const I18N_SOURCE = join(SRC, 'i18n.js');
const PROFILE_SOURCE = join(SRC, 'pages', 'ProfileView.jsx');
const MAIN_SOURCE = join(SRC, 'main.jsx');
const API_ERROR_SOURCE = join(SRC, 'utils', 'apiError.js');
const API_ERROR_INSTALLER = join(SRC, 'utils', 'installApiErrorLocalization.js');
const INDEX_HTML = join(ROOT, 'index.html');
const SOURCE_EXTENSIONS = new Set(['.js', '.jsx']);
const failures = [];

const forbiddenRuntimeFragments = [
  ['LanguageDetector', 'language auto-detection must stay disabled in Spanish-only v1.0'],
  ['./locales/en.json', 'English catalog must not be registered in production'],
  ['changeLanguage(', 'runtime language switching must not be reintroduced while English is unsupported'],
];

const forbiddenEnglishUi = [
  /Are you sure\?/i,
  /Error sending message/i,
  /Skip to main content/i,
  /This screen could not be loaded/i,
  /Save Changes/i,
  /User Profile/i,
  /Receive email notifications/i,
  /New password \(leave blank/i,
  /Music (?:on|off)/i,
  /Sound effects (?:on|off)/i,
  /Real-time strategy/i,
  /Go to city/i,
  />\s*English\s*</i,
];

async function exists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

function flattenCatalog(value, prefix = '', result = new Set()) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) {
      flattenCatalog(child, prefix ? `${prefix}.${key}` : key, result);
    }
  } else if (prefix) {
    result.add(prefix);
  }
  return result;
}

const catalog = JSON.parse(await readFile(ES_CATALOG, 'utf8'));
const catalogKeys = flattenCatalog(catalog);
if (catalogKeys.size === 0) failures.push('es.json: Spanish catalog is empty');

if (await exists(EN_CATALOG)) {
  failures.push('src/locales/en.json: English catalog is still deployable; v1.0 intentionally ships Spanish only');
}

const i18nSource = await readFile(I18N_SOURCE, 'utf8');
if (!/\blng\s*:\s*['"]es['"]/.test(i18nSource)) failures.push('src/i18n.js: runtime locale is not pinned to es');
if (!/supportedLngs\s*:\s*\[\s*['"]es['"]\s*\]/.test(i18nSource)) failures.push('src/i18n.js: supportedLngs must contain only es');
for (const [fragment, message] of forbiddenRuntimeFragments) {
  if (i18nSource.includes(fragment)) failures.push(`src/i18n.js: ${message}`);
}

const profileSource = await readFile(PROFILE_SOURCE, 'utf8');
if (/name\s*=\s*['"]language['"]|value\s*=\s*['"]en['"]|changeLanguage\s*\(/.test(profileSource)) {
  failures.push('src/pages/ProfileView.jsx: unsupported language selection/switching is exposed');
}

const indexSource = await readFile(INDEX_HTML, 'utf8');
if (!/<html\s+lang=['"]es['"]/.test(indexSource)) failures.push('index.html: document language must remain es');

if (!(await exists(API_ERROR_SOURCE)) || !(await exists(API_ERROR_INSTALLER))) {
  failures.push('src/utils: centralized API error localization must remain installed for Spanish-only v1.0');
} else {
  const [apiErrorSource, installerSource, mainSource] = await Promise.all([
    readFile(API_ERROR_SOURCE, 'utf8'),
    readFile(API_ERROR_INSTALLER, 'utf8'),
    readFile(MAIN_SOURCE, 'utf8'),
  ]);
  if (!apiErrorSource.includes('Incorrect username or password') || !apiErrorSource.includes('Usuario o contraseña incorrectos.')) {
    failures.push('src/utils/apiError.js: known authentication error translation is missing');
  }
  if (!apiErrorSource.includes('No se pudo completar la operación.')) {
    failures.push('src/utils/apiError.js: unknown/non-textual API errors must have a Spanish fallback');
  }
  if (!installerSource.includes('interceptors.response.use') || !installerSource.includes('localizeAxiosError')) {
    failures.push('src/utils/installApiErrorLocalization.js: global Axios error normalization is not installed');
  }
  if (!mainSource.includes("./utils/installApiErrorLocalization")) {
    failures.push('src/main.jsx: API error localization must load before the UI mounts');
  }
}

async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      await walk(path);
      continue;
    }
    if (!SOURCE_EXTENSIONS.has(extname(entry.name))) continue;

    const source = await readFile(path, 'utf8');
    const display = relative(ROOT, path);

    for (const [fragment, message] of forbiddenRuntimeFragments) {
      if (source.includes(fragment) && path !== I18N_SOURCE) failures.push(`${display}: ${message}`);
    }

    for (const pattern of forbiddenEnglishUi) {
      if (pattern.test(source)) failures.push(`${display}: retired English UI text matched ${pattern}`);
    }

    for (const match of source.matchAll(/\bt\(\s*['"]([^'"]+)['"]/g)) {
      const key = match[1];
      if (!catalogKeys.has(key)) failures.push(`${display}: missing Spanish translation key ${key}`);
    }
  }
}

await walk(SRC);

if (failures.length) {
  console.error('BM-0083 localization policy failed:');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log(`BM-0083 localization policy passed: Spanish-only runtime, ${catalogKeys.size} catalog leaves, centralized API error localization, no retired English UI markers, and all static t() keys resolve`);
