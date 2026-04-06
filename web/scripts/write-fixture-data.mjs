import {mkdir, stat, writeFile} from "node:fs/promises";
import {resolve} from "node:path";

const root = resolve(import.meta.dirname, "..");
const dataDir = resolve(root, "public/data");
const manifestPath = resolve(dataDir, "players_manifest.json");
const historyDir = resolve(dataDir, "player-history");
const force = process.argv.includes("--force");

const manifest = {
  metadata: {
    compact: false,
    manifest: true,
    metric_order: ["avg", "hr", "rbi", "ops", "war", "era", "strikeouts", "whip"],
    metrics: [
      {key: "avg", label: "Batting Avg", format: "average"},
      {key: "hr", label: "Home Runs", format: "integer"},
      {key: "rbi", label: "RBI", format: "integer"},
      {key: "ops", label: "OPS", format: "average"},
      {key: "war", label: "WAR", format: "decimal"},
      {key: "era", label: "ERA", format: "average"},
      {key: "strikeouts", label: "Strikeouts", format: "integer"},
      {key: "whip", label: "WHIP", format: "average"}
    ],
    notes: ["Fixture dataset generated for CI builds."],
    selection_mode: "fixture"
  },
  players: [
    {i: "fg-10155", n: "Mike Trout", f: 10155, y: [2011, 2024], r: "hitter"},
    {i: "fg-2036", n: "Clayton Kershaw", f: 2036, y: [2008, 2025], r: "pitcher"},
    {i: "fg-13611", n: "Mookie Betts", f: 13611, y: [2014, 2025], r: "hitter"},
    {i: "fg-19755", n: "Aaron Judge", f: 19755, y: [2016, 2025], r: "hitter"},
    {i: "fg-11579", n: "Jose Altuve", f: 11579, y: [2011, 2025], r: "hitter"}
  ]
};

const histories = {
  "fg-10155": {
    k: "mike-trout",
    n: "Mike Trout",
    f: 10155,
    s: [
      [2023, "hitter", "LAA", [0.263, 18, 44, 0.858, 3.0, null, 90, null], [["note", "Wrist injury", "Missed time"]], "Strong when healthy."]
    ]
  },
  "fg-2036": {
    k: "clayton-kershaw",
    n: "Clayton Kershaw",
    f: 2036,
    s: [
      [2023, "pitcher", "LAD", [null, null, null, null, 2.3, 2.46, 137, 1.063], [["note", "Shoulder return", "Came back late"]], "Still elite in shorter outings."]
    ]
  },
  "fg-13611": {
    k: "mookie-betts",
    n: "Mookie Betts",
    f: 13611,
    s: [
      [2023, "hitter", "LAD", [0.307, 39, 107, 0.987, 8.3, null, 107, null], [["team_change", "Settled at shortstop", "Expanded defensive role"]], "MVP-caliber season."]
    ]
  },
  "fg-19755": {
    k: "aaron-judge",
    n: "Aaron Judge",
    f: 19755,
    s: [
      [2023, "hitter", "NYY", [0.267, 37, 75, 1.019, 4.5, null, 106, null], [], "Massive power even in limited games."]
    ]
  },
  "fg-11579": {
    k: "jose-altuve",
    n: "Jose Altuve",
    f: 11579,
    s: [
      [2023, "hitter", "HOU", [0.311, 17, 51, 0.915, 4.7, null, 77, null], [], "High-contact bounce back."]
    ]
  }
};

if (!force) {
  try {
    await stat(manifestPath);
    await stat(historyDir);
    console.log("Existing frontend data found; leaving it in place.");
    process.exit(0);
  } catch {
    // Data is missing, so we fall through and write fixtures.
  }
}

await mkdir(historyDir, {recursive: true});
await writeFile(manifestPath, JSON.stringify(manifest), "utf-8");

for (const [playerId, payload] of Object.entries(histories)) {
  await writeFile(resolve(historyDir, `${playerId}.json`), JSON.stringify(payload), "utf-8");
}

console.log(`Wrote fixture frontend data for ${Object.keys(histories).length} players.`);
