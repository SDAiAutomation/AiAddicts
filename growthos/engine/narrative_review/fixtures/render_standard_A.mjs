// Rend le prompt système Standard "A" (buildManualSystemPrompt) depuis un checkout de growthos-web, SANS chemin local ni dépendance
// externe : uniquement Node >= 22.13 (node:module.stripTypeScriptTypes) et les fichiers sources du checkout passé en argument.
//
//   node render_standard_A.mjs --checkout <growthos-web au commit figé> --language fr --platform youtube --profile standard --out <fichier>
//
// Il assemble, par MARQUEURS (pas par numéros de ligne), les morceaux de sources dont dépend le builder, retire les types TypeScript,
// charge le module dans un dossier temporaire neuf et écrit le texte rendu (fins de ligne LF, UTF-8). Il ne lit rien d'autre, n'écrit
// que --out et son dossier temporaire, et n'ouvre aucune connexion réseau.
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, v, i, all) => (v.startsWith("--") ? [...acc, [v.slice(2), all[i + 1]]] : acc), []));
for (const k of ["checkout", "language", "platform", "profile", "out"]) if (!args[k]) throw new Error(`missing --${k}`);

const read = (rel) => readFileSync(join(args.checkout, rel), "utf8").replace(/\r\n/g, "\n");
const once = (text, marker, label) => {
  const first = text.indexOf(marker);
  if (first < 0 || text.indexOf(marker, first + 1) >= 0) throw new Error(`marker for ${label} must appear exactly once`);
  return first;
};

// 1. Le builder et ses constantes (de `function buildBasePrompt(` jusqu'à la section suivante du fichier)
const actions = read("src/app/(app)/content/ai-actions.ts");
const blockStart = once(actions, "function buildBasePrompt(", "buildBasePrompt");
const blockEnd = once(actions, "\n// Format anthologie", "end of manual prompt section");
const block = actions.slice(blockStart, blockEnd);

// 2. Longueurs de script (imports retirés ; le module est autonome)
const scriptLength = read("src/lib/script-length.ts").split("\n").filter((l) => !l.startsWith("import ")).join("\n");

// 3. Règles du narrateur (constantes exportées, avant le prompt de revue)
const perspective = read("src/lib/narrative-perspective.ts");
const narrator = perspective.slice(0, once(perspective, "const REVIEW_PROMPT", "REVIEW_PROMPT"));

// 4. Règle de priorité par niche (déclaration + son littéral de chaîne)
const niche = read("src/lib/niche-narrative.ts");
const precedence = niche.match(/export const PRECEDENCE_RULE =\s*"(?:[^"\\]|\\.)*"/);
if (!precedence) throw new Error("PRECEDENCE_RULE literal not found");

// 5. Noms de langue (tableau LANGUAGES + LANGUAGE_NAME tels que définis dans le checkout)
const styles = read("src/app/(app)/content/visual-styles.ts");
const langStart = once(styles, "export const LANGUAGES", "LANGUAGES");
const langEnd = styles.indexOf("\n]", langStart);
const fnStart = once(styles, "export function LANGUAGE_NAME", "LANGUAGE_NAME");
const fnEnd = styles.indexOf("\n}", fnStart);
if (langEnd < 0 || fnEnd < 0) throw new Error("could not delimit LANGUAGES or LANGUAGE_NAME");
const languages = styles.slice(langStart, langEnd + 2) + "\n" + styles.slice(fnStart, fnEnd + 2);

const source = [narrator, precedence[0], scriptLength, languages, block, "export { buildManualSystemPrompt }"].join("\n\n");
const dir = mkdtempSync(join(tmpdir(), "baseline-A-"));
try {
  const file = join(dir, "builder.mjs");
  writeFileSync(file, stripTypeScriptTypes(source), "utf8");
  const mod = await import(pathToFileURL(file).href);
  const text = mod.buildManualSystemPrompt(args.language, args.platform, args.profile);
  if (typeof text !== "string" || text.length < 1000 || /undefined|\$\{/.test(text)) throw new Error("rendered prompt looks invalid");
  writeFileSync(args.out, text, "utf8");
  console.log(createHash("sha256").update(text).digest("hex"), text.length);
} finally {
  rmSync(dir, { recursive: true, force: true });
}
