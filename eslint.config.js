/** @type {import('eslint').Linter.Config[]} */
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import prettierConfig from 'eslint-config-prettier';

export default tseslint.config(
  {
    ignores: [
      'dist/',
      'build/',
      '.wrangler/',
      'node_modules/',
      'coverage/',
      '*.config.ts',
      'wrangler.toml',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  prettierConfig,
  {
    files: ['**/*.ts', '**/*.tsx', '**/*.js', '**/*.jsx'],
    languageOptions: {
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
    rules: {
      // Security: enforce no-console in production code paths.
      'no-console': 'warn',
    },
  }
);
