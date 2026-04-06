import {stat} from "node:fs/promises";
import {resolve} from "node:path";

const root = resolve(import.meta.dirname, "..");
const dataDir = resolve(root, "public/data");

await stat(resolve(dataDir, "players_manifest.json"));
await stat(resolve(dataDir, "player-history"));
