import { readFile } from 'node:fs/promises';

const i18nSource = await readFile(new URL('../src/i18n.js', import.meta.url), 'utf8');
const profileSource = await readFile(new URL('../src/pages/ProfileView.jsx', import.meta.url), 'utf8');
const violations = [];

if (/locales\/en\.json/.test(i18nSource)) {
  violations.push('English locale is imported by production i18n runtime');
}
if (!/supportedLngs:\s*\[\s*['"]es['"]\s*\]/.test(i18nSource)) {
  violations.push('Production i18n must explicitly support Spanish only');
}
if (!/lng:\s*['"]es['"]/.test(i18nSource) || !/fallbackLng:\s*['"]es['"]/.test(i18nSource)) {
  violations.push('Production i18n language and fallback must both be Spanish');
}
if (/value=['"]en['"]/.test(profileSource) || /name=['"]language['"]/.test(profileSource)) {
  violations.push('Profile exposes a production language selector');
}

if (violations.length) {
  console.error('Localization policy failed:\n' + violations.join('\n'));
  process.exit(1);
}

console.log('Localization policy passed: Spanish is the only production locale');
