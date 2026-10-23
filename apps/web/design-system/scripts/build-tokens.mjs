// Gera CSS a partir de design-system/tokens.json (a única fonte dos valores).
//
//   node design-system/scripts/build-tokens.mjs            → src/design-system/tokens.css (painel)
//   node design-system/scripts/build-tokens.mjs --check    → falha se o CSS commitado estiver desatualizado
//   node design-system/scripts/build-tokens.mjs --artifact <saida.css>
//        → layout "compilado" do artefato de design system (fontes em fonts/)
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const tokens = JSON.parse(readFileSync(resolve(root, "tokens.json"), "utf8"));
const appOutput = resolve(root, "../src/design-system/tokens.css");

const themes = tokens.color.themes.map((theme) => theme.id);
const [firstTheme] = themes;

function colorValue(value) {
  return value.replace(/^\{(.+)\}$/, "var(--$1)");
}

function valueFor(token, theme) {
  if (typeof token.value === "string") return token.value;
  return token.value[theme] ?? token.value[firstTheme];
}

function themedBlock(theme) {
  const themed = [...tokens.color.tokens, ...(tokens.shadow?.tokens ?? [])];
  return themed
    .filter((token) => theme === firstTheme || valueFor(token, theme) !== valueFor(token, firstTheme) || /^\{/.test(valueFor(token, theme)))
    .map((token) => `  --${token.name}: ${colorValue(valueFor(token, theme))};`)
    .join("\n");
}

function staticBlock() {
  const lines = [];
  for (const family of ["spacing", "radius"]) {
    for (const token of tokens[family].tokens) lines.push(`  --${token.name}: ${token.value};`);
  }
  for (const [key, stack] of Object.entries(tokens.type.families)) lines.push(`  --font-${key}: ${stack};`);
  return lines.join("\n");
}

function fontFaces(urlFor) {
  return tokens.type.fonts
    .map(
      (font) => `@font-face {
  font-family: "${font.family}";
  font-style: ${font.style ?? "normal"};
  font-weight: ${font.weight};
  font-display: swap;
  src: url("${urlFor(font.file)}") format("woff2");
}`,
    )
    .join("\n\n");
}

function typeClasses() {
  const blocks = [];
  for (const group of tokens.type.groups) {
    for (const style of group.styles) {
      const props = [`  font-family: var(--font-${style.family ?? group.family});`, `  font-size: ${style.fontSize};`];
      if (style.lineHeight) props.push(`  line-height: ${style.lineHeight};`);
      if (style.fontWeight) props.push(`  font-weight: ${style.fontWeight};`);
      if (style.letterSpacing) props.push(`  letter-spacing: ${style.letterSpacing};`);
      if (style.name === "text-label") props.push("  text-transform: uppercase;");
      blocks.push(`.${style.name} {\n${props.join("\n")}\n}`);
    }
  }
  return blocks.join("\n\n");
}

function appCss() {
  const dark = themedBlock("dark");
  return `/* Gerado por design-system/scripts/build-tokens.mjs a partir de design-system/tokens.json. Não edite à mão. */

${fontFaces((file) => `../../design-system/${file}`)}

:root {
${themedBlock(firstTheme)}
${staticBlock()}
  color-scheme: light;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
${dark.replace(/^/gm, "  ")}
    color-scheme: dark;
  }
}

:root[data-theme="dark"] {
${dark}
  color-scheme: dark;
}

${typeClasses()}
`;
}

function artifactCss() {
  const blocks = themes
    .slice(1)
    .map((theme) => `[data-theme="${theme}"] {\n${themedBlock(theme)}\n  color-scheme: dark;\n}`)
    .join("\n\n");
  return `/* ${tokens.name} — generated from tokens.json */
:root, [data-theme="${firstTheme}"] {
${themedBlock(firstTheme)}
}

${blocks}

:root {
${staticBlock()}
}

${typeClasses()}

${fontFaces((file) => file)}
`;
}

const args = process.argv.slice(2);
if (args[0] === "--artifact") {
  writeFileSync(resolve(args[1]), artifactCss());
} else if (args[0] === "--check") {
  if (readFileSync(appOutput, "utf8") !== appCss()) {
    console.error("src/design-system/tokens.css desatualizado: rode npm run tokens");
    process.exit(1);
  }
} else {
  writeFileSync(appOutput, appCss());
}
