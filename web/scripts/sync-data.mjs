import {spawn} from "node:child_process";
import {stat} from "node:fs/promises";
import {isAbsolute, resolve} from "node:path";

const webRoot = resolve(import.meta.dirname, "..");
const repoRoot = resolve(webRoot, "..");
const dataDir = resolve(webRoot, "public/data");
const manifestPath = resolve(dataDir, "players_manifest.json");
const historyDir = resolve(dataDir, "player-history");
const playersSnapshotPath = resolve(dataDir, "players.json");
const defaultProcessedOutput = resolve(repoRoot, "data/processed/players.json");
const defaultPlayersCsv = resolve(repoRoot, "config/players.example.csv");
const defaultAnnotationsCsv = resolve(repoRoot, "config/annotations.example.csv");
const defaultPythonBin = resolve(repoRoot, ".venv/bin/python");
const defaultPybaseballCache = resolve(repoRoot, "data/raw/pybaseball-cache");

const options = parseArgs(process.argv.slice(2));

if (options.help) {
  printHelp();
  process.exit(0);
}

if (options.generate) {
  await runPipelineAndPopulateFrontend(options);
}

await stat(manifestPath);
await stat(historyDir);

function parseArgs(argv) {
  const parsed = {
    generate: false,
    allPlayers: false,
    playersCsv: null,
    annotationsCsv: null,
    processedOutput: null,
    startYear: null,
    endYear: null,
    sourcePreference: "mlb_statsapi",
    help: false
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    switch (arg) {
      case "--generate":
        parsed.generate = true;
        break;
      case "--all-players":
        parsed.allPlayers = true;
        break;
      case "--players":
        parsed.playersCsv = getValue(argv, ++index, "--players");
        break;
      case "--annotations":
        parsed.annotationsCsv = getValue(argv, ++index, "--annotations");
        break;
      case "--processed-output":
        parsed.processedOutput = getValue(argv, ++index, "--processed-output");
        break;
      case "--start-year":
        parsed.startYear = getValue(argv, ++index, "--start-year");
        break;
      case "--end-year":
        parsed.endYear = getValue(argv, ++index, "--end-year");
        break;
      case "--source-preference":
        parsed.sourcePreference = getValue(argv, ++index, "--source-preference");
        break;
      case "--help":
      case "-h":
        parsed.help = true;
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return parsed;
}

function getValue(argv, index, flagName) {
  if (index >= argv.length) {
    throw new Error(`Missing value for ${flagName}`);
  }
  return argv[index];
}

function toAbs(pathValue) {
  if (!pathValue) {
    return null;
  }
  return isAbsolute(pathValue) ? pathValue : resolve(repoRoot, pathValue);
}

async function runPipelineAndPopulateFrontend(options) {
  const pythonBin = await resolvePythonBin();
  const processedOutput = toAbs(options.processedOutput) ?? defaultProcessedOutput;
  const playersCsv = toAbs(options.playersCsv) ?? defaultPlayersCsv;
  const annotationsCsv = toAbs(options.annotationsCsv) ?? defaultAnnotationsCsv;
  const buildDatasetScript = resolve(repoRoot, "scripts/build_player_dataset.py");
  const buildStoreScript = resolve(repoRoot, "scripts/build_frontend_store.py");

  const datasetArgs = [
    buildDatasetScript,
    "--annotations",
    annotationsCsv,
    "--source-preference",
    options.sourcePreference ?? "mlb_statsapi",
    "--processed-output",
    processedOutput,
    "--frontend-output",
    playersSnapshotPath
  ];

  if (options.allPlayers) {
    datasetArgs.push("--all-players");
  } else {
    datasetArgs.push("--players", playersCsv);
  }

  if (options.startYear) {
    datasetArgs.push("--start-year", options.startYear);
  }
  if (options.endYear) {
    datasetArgs.push("--end-year", options.endYear);
  }

  const runtimeEnv = {
    PYBASEBALL_CACHE: process.env.PYBASEBALL_CACHE ?? defaultPybaseballCache,
    MPLCONFIGDIR: process.env.MPLCONFIGDIR ?? "/tmp/matplotlib-cache"
  };

  let usedStaleProcessedSnapshot = false;
  try {
    await run(pythonBin, datasetArgs, repoRoot, runtimeEnv);
  } catch (error) {
    if (!(await exists(processedOutput))) {
      throw error;
    }
    usedStaleProcessedSnapshot = true;
    console.warn(
      `Data generation failed (${error instanceof Error ? error.message : String(error)}). ` +
        `Falling back to existing processed snapshot at ${processedOutput}.`
    );
  }

  await run(pythonBin, [
    buildStoreScript,
    "--input",
    processedOutput,
    "--manifest-output",
    manifestPath,
    "--history-dir",
    historyDir
  ], repoRoot, runtimeEnv);

  if (usedStaleProcessedSnapshot) {
    console.warn("Frontend data store rebuilt from last-known-good processed snapshot.");
  }
}

function run(command, args, cwd, env = undefined) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      cwd,
      stdio: "inherit",
      env: env ? {...process.env, ...env} : process.env
    });

    child.on("error", rejectPromise);
    child.on("close", (code) => {
      if (code === 0) {
        resolvePromise();
        return;
      }
      rejectPromise(new Error(`${command} exited with code ${code}`));
    });
  });
}

async function resolvePythonBin() {
  const fromEnv = process.env.PYTHON_BIN;
  if (fromEnv) {
    return fromEnv;
  }
  if (await exists(defaultPythonBin)) {
    return defaultPythonBin;
  }
  return "python3";
}

async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

function printHelp() {
  console.log(`Usage: node scripts/sync-data.mjs [options]

Validates that frontend data is present, and optionally regenerates it first.

Options:
  --generate             Run Python pipeline and rebuild frontend data files.
  --all-players          Use all-player dataset mode when generating.
  --players <path>       Players CSV for non-all-player generation.
  --annotations <path>   Annotation CSV path.
  --processed-output <path>  Processed dataset JSON path.
  --start-year <year>    Optional lower year bound for generation.
  --end-year <year>      Optional upper year bound for generation.
  --source-preference <source>  mlb_statsapi | auto | fangraphs.
  --help                 Show this help output.
`);
}
