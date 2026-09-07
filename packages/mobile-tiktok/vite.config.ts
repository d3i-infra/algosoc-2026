import { readFileSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { defineConfig } from "vite";

const dirname = fileURLToPath(new URL(".", import.meta.url));
const pkg = JSON.parse(readFileSync(path.join(dirname, "package.json"), "utf8")) as { version: string };

export default defineConfig({
  base: "./",
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  build: {
    target: "safari12",
    modulePreload: { polyfill: false },
    cssTarget: "safari12",
    // The dev server still serves public/fake-host.html, but the release
    // build must not ship it: Playwright's webServer copies it into dist/
    // explicitly for the flow tests. See ADR-0041 (no fake host in the
    // participant-facing artifact).
    copyPublicDir: false,
    rollupOptions: {
      output: {
        codeSplitting: false,
        entryFileNames: "assets/app.js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
  server: {
    port: 3100,
    strictPort: true,
    fs: {
      allow: [".", path.resolve(dirname, "../python/port/configs")],
      // "." above covers the whole package (src, public, node_modules) for
      // the dev server; fixtures/ddp holds real, un-synthetic participant
      // exports (ADR-0041, ADR-0014) and must stay unreachable even though
      // it lives under the package root, so it is explicitly denied on top
      // of vite's own default deny list.
      deny: [
        ".env", ".env.*", "*.{crt,pem,key,p12,pfx,cer,der}", ".npmrc", ".yarnrc.yml", "**/.git/**",
        "**/fixtures/ddp/**",
      ],
    },
  },
  preview: { port: 3100, strictPort: true },
});
