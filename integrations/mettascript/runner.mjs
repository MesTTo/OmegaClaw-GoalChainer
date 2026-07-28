import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

const PROTOCOL = "goalchainer-mettascript-runner-v1";
const MAX_REQUEST_BYTES = 2 * 1024 * 1024;
const MAX_RESULT_COUNT = 256;
const MAX_RESULT_CHARS = 2 * 1024 * 1024;
let mettaScript;

function fail(message, details = {}) {
  process.stderr.write(`${JSON.stringify({ protocol: PROTOCOL, message, details })}\n`);
  process.exitCode = 1;
}

function positiveInteger(value, fallback, name) {
  const selected = value === undefined ? fallback : value;
  if (!Number.isSafeInteger(selected) || selected <= 0) {
    throw new Error(`${name} must be a positive safe integer`);
  }
  return selected;
}

async function loadMeTTaScript() {
  const packageRoot = path.join(process.cwd(), "package.json");
  const resolveFromRoot = createRequire(pathToFileURL(packageRoot));
  const entry = resolveFromRoot.resolve("@mettascript/node");
  return import(pathToFileURL(entry).href);
}

// MeTTaScript keeps its own @doc atoms outside the evaluation environment.
// Apply the same stdlib convention to application documentation.
function evaluationSource(source) {
  const { format, isExpr, isSym, parseAll, standardTokenizer } = mettaScript;
  return parseAll(source, standardTokenizer())
    .filter(({ atom }) => {
      const head = isExpr(atom) ? atom.items[0] : undefined;
      return !(head !== undefined && isSym(head) && head.name === "@doc");
    })
    .map(({ atom, bang }) => `${bang ? "!" : ""}${format(atom)}`)
    .join("\n");
}

async function readRequest() {
  const chunks = [];
  let size = 0;
  for await (const chunk of process.stdin) {
    size += chunk.length;
    if (size > MAX_REQUEST_BYTES) {
      throw new Error(`request exceeds ${MAX_REQUEST_BYTES} bytes`);
    }
    chunks.push(chunk);
  }
  const request = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  if (
    request === null ||
    typeof request !== "object" ||
    Array.isArray(request) ||
    request.protocol !== PROTOCOL ||
    typeof request.source !== "string"
  ) {
    throw new Error("request has the wrong protocol or shape");
  }
  return request;
}

function evaluate(request) {
  const { format, runSource } = mettaScript;
  const fuel = positiveInteger(request.fuel, 500, "fuel");
  const maxSteps = positiveInteger(request.maxSteps, 1_000_000, "maxSteps");
  const maxStackDepth = positiveInteger(
    request.maxStackDepth,
    1_024,
    "maxStackDepth",
  );
  const groups = runSource(evaluationSource(request.source), fuel, new Map(), {
    tabling: request.tabling !== false,
    maxSteps,
    maxStackDepth,
  });
  const rows = groups.flatMap((group) => group.results.map(format));
  if (rows.length > MAX_RESULT_COUNT) {
    throw new Error(`result count exceeds ${MAX_RESULT_COUNT}`);
  }
  const resultChars = rows.reduce((total, row) => total + row.length, 0);
  if (resultChars > MAX_RESULT_CHARS) {
    throw new Error(`result text exceeds ${MAX_RESULT_CHARS} characters`);
  }
  return rows;
}

async function checkAdapter() {
  const adapterUrl = new URL(
    "../threadkeeper/goalchainer_threadkeeper.metta",
    import.meta.url,
  );
  const source = await readFile(adapterUrl, "utf8");
  const rows = evaluate({
    source: `${source}\n!(gc-thread-release 200 199 True)\n`,
  });
  const expected =
    '(goalchainer-thread-v1 release ok (release False "not-before constraint has not elapsed"))';
  if (rows.length !== 1 || rows[0] !== expected) {
    throw new Error(`adapter check returned ${JSON.stringify(rows)}`);
  }
  process.stdout.write(`${expected}\n`);
}

try {
  mettaScript = await loadMeTTaScript();
  if (process.argv.includes("--check")) {
    await checkAdapter();
  } else {
    const request = await readRequest();
    const rows = evaluate(request);
    process.stdout.write(`${JSON.stringify({ protocol: PROTOCOL, rows })}\n`);
  }
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
}
