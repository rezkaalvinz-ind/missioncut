import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  { files: ["**/*.{ts,tsx}"], languageOptions: { globals: { ...globals.browser, ...globals.node } } },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
);
