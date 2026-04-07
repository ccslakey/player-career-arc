import {put} from "@vercel/blob";
import {readdir, readFile, stat} from "node:fs/promises";
import {relative, resolve, sep} from "node:path";

const webRoot = resolve(import.meta.dirname, "..");

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

let manifestUrl = null;
let uploaded = 0;
let failed = 0;
let nextIndex = 0;

const workers = Array.from({length: options.concurrency}, () => runWorker());
await Promise.all(workers);

if (failed > 0) {
  throw new Error(`Blob upload finished with ${failed} failed file(s).`);
}

console.log(`Uploaded ${uploaded} JSON files to prefix "${normalizedPrefix}".`);

if (manifestUrl) {
  const baseUrl = manifestUrl.replace(/\/players_manifest\.json$/, "");
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
        const result = await put(blobPath, payload, {
          access: "public",
          token,
          addRandomSuffix: false,
          allowOverwrite: true,
          contentType: "application/json",
          cacheControlMaxAge
        });

        if (relativePath === "players_manifest.json") {
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

function cacheTtl(relativePath, mutable) {
  if (relativePath === "players_manifest.json") {
    return mutable ? 60 : 31536000;
  }
  if (relativePath.startsWith("player-history/")) {
    return mutable ? 3600 : 31536000;
  }
  return mutable ? 3600 : 31536000;
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

function parseArgs(argv) {
  const parsed = {
    source: "public/data",
    prefix: "latest",
    concurrency: 12,
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
  --token <token>        Vercel Blob read/write token (or use BLOB_READ_WRITE_TOKEN env var)
  --dry-run              Show planned uploads without writing blobs
  --help                 Show help
`);
}
