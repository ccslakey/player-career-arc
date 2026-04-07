import {BlobServiceNotAvailable, BlobServiceRateLimited, BlobUnknownError, put} from "@vercel/blob";
import {readdir, readFile, stat} from "node:fs/promises";
import {relative, resolve, sep} from "node:path";

const webRoot = resolve(import.meta.dirname, "..");
const MANIFEST_FILE = "players_manifest.json";
const DATA_VERSION_FILE = "data-version.json";
const DEFAULT_MAX_UPLOAD_ATTEMPTS = 6;
const DEFAULT_BASE_BACKOFF_MS = 500;
const DEFAULT_MAX_BACKOFF_MS = 30_000;

const options = parseArgs(process.argv.slice(2));

if (options.help) {
  printHelp();
  process.exit(0);
}

const sourceDir = resolve(webRoot, options.source);
await stat(sourceDir);

const files = await listFiles(sourceDir);
const jsonFiles = files.filter((filePath) => filePath.endsWith(".json"));

if (!jsonFiles.length) {
  throw new Error(`No JSON files found under ${sourceDir}`);
}

const normalizedPrefix = normalizePrefix(options.prefix);
const token = options.token || process.env.BLOB_READ_WRITE_TOKEN;

if (!options.dryRun && !token) {
  throw new Error("Missing BLOB_READ_WRITE_TOKEN. Set it in the environment or pass --token.");
}

const mutablePrefix = normalizedPrefix === "latest" || normalizedPrefix.startsWith("latest/");
const dataVersionPayload = await buildDataVersionPayload({
  sourceDir,
  prefix: normalizedPrefix
});

let manifestUrl = null;
let versionUrl = null;
let uploaded = 0;
let failed = 0;
let nextIndex = 0;

const workers = Array.from({length: options.concurrency}, () => runWorker());
await Promise.all(workers);

if (failed > 0) {
  throw new Error(`Blob upload finished with ${failed} failed file(s).`);
}

if (options.dryRun) {
  console.log(`[dry-run] ${DATA_VERSION_FILE} -> ${normalizedPrefix}/${DATA_VERSION_FILE}`);
  uploaded += 1;
} else {
  const cacheControlMaxAge = cacheTtl(DATA_VERSION_FILE, mutablePrefix);
  const result = await putWithRetries({
    blobPath: `${normalizedPrefix}/${DATA_VERSION_FILE}`,
    relativePath: DATA_VERSION_FILE,
    payload: JSON.stringify(dataVersionPayload),
    cacheControlMaxAge,
    token
  });
  versionUrl = result.url;
  uploaded += 1;
  console.log(`[upload] ${DATA_VERSION_FILE} -> ${normalizedPrefix}/${DATA_VERSION_FILE} (ttl ${cacheControlMaxAge}s)`);
}

console.log(`Uploaded ${uploaded} JSON files to prefix "${normalizedPrefix}".`);

if (manifestUrl || versionUrl) {
  const baseUrl = (manifestUrl ?? versionUrl).replace(/\/[^/]+$/, "");
  console.log(`Data base URL: ${baseUrl}`);
}

async function runWorker() {
  while (true) {
    const fileIndex = nextIndex;
    nextIndex += 1;
    if (fileIndex >= jsonFiles.length) {
      return;
    }

    const filePath = jsonFiles[fileIndex];
    const relativePath = relative(sourceDir, filePath).split(sep).join("/");
    const blobPath = `${normalizedPrefix}/${relativePath}`;
    const cacheControlMaxAge = cacheTtl(relativePath, mutablePrefix);

    try {
      if (options.dryRun) {
        console.log(`[dry-run] ${relativePath} -> ${blobPath}`);
      } else {
        const payload = await readFile(filePath);
        const result = await putWithRetries({
          blobPath,
          relativePath,
          payload,
          cacheControlMaxAge,
          token
        });

        if (relativePath === MANIFEST_FILE) {
          manifestUrl = result.url;
        }

        console.log(`[upload] ${relativePath} -> ${blobPath} (ttl ${cacheControlMaxAge}s)`);
      }

      uploaded += 1;
    } catch (error) {
      failed += 1;
      console.error(`[error] Failed upload for ${relativePath}:`, error);
    }
  }
}

async function putWithRetries({
  blobPath,
  relativePath,
  payload,
  cacheControlMaxAge,
  token
}) {
  for (let attempt = 1; attempt <= DEFAULT_MAX_UPLOAD_ATTEMPTS; attempt += 1) {
    try {
      return await put(blobPath, payload, {
        access: "public",
        token,
        addRandomSuffix: false,
        allowOverwrite: true,
        contentType: "application/json",
        cacheControlMaxAge
      });
    } catch (error) {
      const waitMs = getRetryDelayMs(error, attempt);
      if (waitMs === null || attempt === DEFAULT_MAX_UPLOAD_ATTEMPTS) {
        throw error;
      }

      console.warn(
        `[retry] ${relativePath} failed on attempt ${attempt}/${DEFAULT_MAX_UPLOAD_ATTEMPTS}; waiting ${waitMs}ms before retry (${errorSummary(error)})`
      );
      await sleep(waitMs);
    }
  }

  throw new Error(`Upload failed after ${DEFAULT_MAX_UPLOAD_ATTEMPTS} attempts for ${relativePath}`);
}

function getRetryDelayMs(error, attempt) {
  if (error instanceof BlobServiceRateLimited) {
    const retryAfterSeconds = Number.isFinite(error.retryAfter) && error.retryAfter > 0 ? error.retryAfter : 60;
    const jitterMs = Math.floor(Math.random() * 750);
    return retryAfterSeconds * 1000 + jitterMs;
  }

  if (error instanceof BlobServiceNotAvailable || error instanceof BlobUnknownError || isNetworkLikeError(error)) {
    const exponential = Math.min(DEFAULT_BASE_BACKOFF_MS * 2 ** (attempt - 1), DEFAULT_MAX_BACKOFF_MS);
    const jitter = Math.floor(Math.random() * Math.max(250, Math.floor(exponential * 0.25)));
    return exponential + jitter;
  }

  return null;
}

function isNetworkLikeError(error) {
  if (error instanceof TypeError) {
    return true;
  }

  const code = typeof error === "object" && error !== null && "code" in error ? String(error.code) : "";
  return ["ECONNRESET", "ETIMEDOUT", "ENOTFOUND", "EAI_AGAIN", "UND_ERR_CONNECT_TIMEOUT"].includes(code);
}

function errorSummary(error) {
  if (error instanceof Error) {
    return `${error.name}: ${error.message}`;
  }
  return String(error);
}

function sleep(ms) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

function cacheTtl(relativePath, mutable) {
  if (relativePath === MANIFEST_FILE || relativePath === DATA_VERSION_FILE) {
    return mutable ? 60 : 31536000;
  }
  if (relativePath.startsWith("player-history/")) {
    return mutable ? 3600 : 31536000;
  }
  return mutable ? 3600 : 31536000;
}

async function buildDataVersionPayload({sourceDir, prefix}) {
  const source = {
    start_year: optionalNumber(options.startYear || process.env.DATA_START_YEAR),
    end_year: optionalNumber(options.endYear || process.env.DATA_END_YEAR)
  };
  const manifestSummary = await loadManifestSummary(sourceDir);

  return {
    uploaded_at: new Date().toISOString(),
    prefix,
    git_sha: process.env.GITHUB_SHA ?? null,
    source,
    manifest: manifestSummary
  };
}

async function loadManifestSummary(sourceDir) {
  const manifestPath = resolve(sourceDir, MANIFEST_FILE);
  try {
    const rawManifest = await readFile(manifestPath, "utf-8");
    const manifest = JSON.parse(rawManifest);
    return {
      player_count: Array.isArray(manifest.players) ? manifest.players.length : undefined,
      metric_count: Array.isArray(manifest.metadata?.metrics) ? manifest.metadata.metrics.length : undefined,
      selection_mode: manifest.metadata?.selection_mode ?? null
    };
  } catch {
    return {
      player_count: undefined,
      metric_count: undefined,
      selection_mode: null
    };
  }
}

async function listFiles(directoryPath) {
  const entries = await readdir(directoryPath, {withFileTypes: true});
  const files = [];

  for (const entry of entries) {
    const fullPath = resolve(directoryPath, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await listFiles(fullPath)));
      continue;
    }
    files.push(fullPath);
  }

  return files;
}

function normalizePrefix(prefix) {
  const normalized = prefix.trim().replace(/^\/+|\/+$/g, "");
  if (!normalized) {
    throw new Error("Prefix must not be empty.");
  }
  return normalized;
}

function optionalNumber(value) {
  if (value == null || value === "") {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseArgs(argv) {
  const parsed = {
    source: "public/data",
    prefix: "latest",
    concurrency: 12,
    startYear: "",
    endYear: "",
    token: "",
    dryRun: false,
    help: false
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    switch (arg) {
      case "--source":
        parsed.source = requiredValue(argv, ++index, "--source");
        break;
      case "--prefix":
        parsed.prefix = requiredValue(argv, ++index, "--prefix");
        break;
      case "--concurrency":
        parsed.concurrency = Number(requiredValue(argv, ++index, "--concurrency"));
        break;
      case "--start-year":
        parsed.startYear = requiredValue(argv, ++index, "--start-year");
        break;
      case "--end-year":
        parsed.endYear = requiredValue(argv, ++index, "--end-year");
        break;
      case "--token":
        parsed.token = requiredValue(argv, ++index, "--token");
        break;
      case "--dry-run":
        parsed.dryRun = true;
        break;
      case "--help":
      case "-h":
        parsed.help = true;
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!Number.isFinite(parsed.concurrency) || parsed.concurrency < 1) {
    throw new Error("--concurrency must be a positive number.");
  }

  return parsed;
}

function requiredValue(argv, index, flagName) {
  if (index >= argv.length) {
    throw new Error(`Missing value for ${flagName}`);
  }
  return argv[index];
}

function printHelp() {
  console.log(`Usage: node scripts/upload-blob-data.mjs [options]

Upload frontend JSON files from web/public/data to Vercel Blob.

Options:
  --source <path>        Source directory to upload (default: public/data)
  --prefix <prefix>      Blob path prefix (default: latest)
  --concurrency <n>      Number of parallel uploads (default: 12)
  --start-year <year>    Optional metadata value written to data-version.json
  --end-year <year>      Optional metadata value written to data-version.json
  --token <token>        Vercel Blob read/write token (or use BLOB_READ_WRITE_TOKEN env var)
  --dry-run              Show planned uploads without writing blobs
  --help                 Show help
`);
}
