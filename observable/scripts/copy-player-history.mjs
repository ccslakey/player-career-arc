import {cp, mkdir, rm} from "node:fs/promises";
import {resolve} from "node:path";

const root = resolve(import.meta.dirname, "..");
const sourceDir = resolve(root, "src/data/player-history");
const targetDir = resolve(root, "dist/_file/data/player-history");

await rm(targetDir, {recursive: true, force: true});
await mkdir(resolve(root, "dist/_file/data"), {recursive: true});
await cp(sourceDir, targetDir, {recursive: true});

