#!/usr/bin/env node

const path = require("path");
const { spawnSync } = require("child_process");

const cliPath = path.join(__dirname, "cli.js");
const result = spawnSync(process.execPath, [cliPath, "tui", ...process.argv.slice(2)], {
  stdio: "inherit",
  env: process.env
});

process.exit(typeof result.status === "number" ? result.status : 1);
