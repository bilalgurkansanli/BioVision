import js from "@eslint/js";
import tseslint from "typescript-eslint";

// `eslint-config-next` still ships the legacy `@rushstack/eslint-patch` shim and
// fails to load under ESLint 9's flat config, so its Next-specific rules are not
// in this config. The two it would have flagged here are both deliberate:
//
//   next/no-img-element   Results render object URLs and API-returned images
//                         with plain <img>. next/image adds an optimiser that
//                         cannot process a blob: URL and would pull in sharp.
//   next/link             Internal navigation already uses next/link.
//
// TypeScript in strict mode does the load-bearing checking; this catches the
// rest. Revisit when eslint-config-next ships a working flat config.
export default tseslint.config(
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    languageOptions: {
      globals: { window: "readonly", document: "readonly", confirm: "readonly" },
    },
  },
);
