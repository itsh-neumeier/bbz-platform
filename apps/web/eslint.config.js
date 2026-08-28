import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import pluginVue from 'eslint-plugin-vue';
import a11y from 'eslint-plugin-vuejs-accessibility';

// Accessibility is a *functional* requirement (RULES.md). The a11y plugin runs
// at error level so keyboard/ARIA regressions fail CI.
export default tseslint.config(
  { ignores: ['dist/', 'coverage/', 'playwright-report/', 'test-results/', 'node_modules/'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  ...a11y.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: { parser: tseslint.parser },
    },
  },
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      'vue/multi-word-component-names': 'off',
    },
  },
);
