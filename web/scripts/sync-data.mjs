import {cp, mkdir, rm, stat} from "node:fs/promises";
import {resolve} from "node:path";

const root = resolve(import.meta.dirname, "..", "..");
const sourceDir = resolve(root, "observable/src/data");
const targetDir = resolve(root, "web/public/data");

await stat(resolve(sourceDir, "players_manifest.json"));
await stat(resolve(sourceDir, "player-history"));

await rm(targetDir, {recursive: true, force: true});
await mkdir(targetDir, {recursive: true});

await cp(resolve(sourceDir, "players_manifest.json"), resolve(targetDir, "players_manifest.json"));
await cp(resolve(sourceDir, "player-history"), resolve(targetDir, "player-history"), {recursive: true});
