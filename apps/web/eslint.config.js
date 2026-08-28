import js from '@eslint/js';
import pluginVue from 'eslint-plugin-vue';
import a11y from 'eslint-plugin-vuejs-accessibility';

// Accessibility is a *functional* requirement (RULES.md). The a11y plugin runs
// at error level so keyboard/ARIA regressions fail CI.
export default [
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  ...a11y.configs['flat/recommended'],
  {
    files: ['**/*.{js,ts,vue}'],
    languageOptions: { ecmaVersion: 2022, sourceType: 'module' },
    rules: {
      'vue/multi-word-component-names': 'off',
    },
  },
  { ignores: ['dist/', 'coverage/', 'playwright-report/'] },
];
