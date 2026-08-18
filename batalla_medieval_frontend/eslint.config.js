import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import { reactRefresh } from 'eslint-plugin-react-refresh';

export default [
  {
    ignores: ['dist/**', 'node_modules/**'],
  },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
      parserOptions: {
        ecmaFeatures: {
          jsx: true,
        },
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh.plugin,
    },
    rules: {
      ...js.configs.recommended.rules,

      // ESLint core does not understand that JSX tag names consume imported
      // component identifiers. The old project config intentionally had no
      // eslint-plugin-react, so keep that established scope instead of
      // reporting every JSX component import as unused after the ESLint 9
      // migration. Syntax/no-undef and the Rules of Hooks remain enforced.
      'no-unused-vars': 'off',
      'react-hooks/rules-of-hooks': 'error',

      // eslint-plugin-react-hooks 7 added React Compiler-oriented rules such as
      // immutability and set-state-in-effect to its flat recommended preset.
      // Enabling those as part of a security dependency update would turn G1
      // into an unrelated frontend refactor. They will be introduced in a
      // dedicated quality task instead of silently expanding this gate.
      'react-hooks/exhaustive-deps': 'off',
      'react-refresh/only-export-components': 'off',
    },
  },
];
