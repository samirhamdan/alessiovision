// Empacota src/ui como um script clássico que define window.AlessioUI, usando o
// React global da página (para as prévias ao vivo do design system).
//
//   node design-system/scripts/build-bundle.mjs <pasta-de-saida>
//   → bundle.js e bundle.css
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const out = resolve(process.argv[2] ?? "dist-ds");
mkdirSync(out, { recursive: true });

const COMPONENTS = [
  "AppHeader",
  "Badge",
  "Button",
  "Callout",
  "DataTable",
  "Logo",
  "NavTabs",
  "Panel",
  "SecretField",
  "SelectField",
  "TextField",
];

// "react" e "react/jsx-runtime" viram leituras de window.React.
const reactGlobal = {
  name: "react-global",
  setup(b) {
    b.onResolve({ filter: /^react(\/jsx-runtime)?$/ }, (args) => ({ path: args.path, namespace: "react-global" }));
    b.onLoad({ filter: /.*/, namespace: "react-global" }, (args) => ({
      loader: "js",
      contents:
        args.path === "react"
          ? "const R = window.React; export default R; export const { useId, useState, useEffect, Fragment } = R;"
          : `const R = window.React;
export const Fragment = R.Fragment;
function create(type, props, key, spread) {
  const { children, ...rest } = props;
  if (key !== undefined) rest.key = key;
  if (children === undefined) return R.createElement(type, rest);
  return spread ? R.createElement(type, rest, ...children) : R.createElement(type, rest, children);
}
export const jsx = (type, props, key) => create(type, props, key, false);
export const jsxs = (type, props, key) => create(type, props, key, true);`,
    }));
  },
};

const result = await build({
  entryPoints: [resolve(web, "src/ui/index.ts")],
  bundle: true,
  format: "iife",
  globalName: "AlessioUI",
  jsx: "automatic",
  minify: true,
  target: "es2020",
  write: false,
  plugins: [reactGlobal],
  define: { "process.env.NODE_ENV": '"production"' },
});

const header = `/* @ds-bundle: ${JSON.stringify({ format: 4, namespace: "AlessioUI", components: COMPONENTS.map((name) => ({ name })) })} */\n`;
const code = `${header}${result.outputFiles[0].text}window.AlessioUI = AlessioUI;\n`;
if (/<\/script|<!--/i.test(code)) throw new Error("bundle contém </script ou <!--");
writeFileSync(resolve(out, "bundle.js"), code);
copyFileSync(resolve(web, "src/ui/ui.css"), resolve(out, "bundle.css"));
console.log(`bundle.js ${(readFileSync(resolve(out, "bundle.js")).length / 1024).toFixed(1)} KB`);
