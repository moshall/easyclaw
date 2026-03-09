#!/usr/bin/env node

const path = require("path");
const { spawnSync } = require("child_process");

function isTrue(value) {
  const text = String(value || "").trim().toLowerCase();
  return text === "1" || text === "true" || text === "yes" || text === "on";
}

function isGlobalInstall() {
  return String(process.env.npm_config_global || "").trim() === "true" ||
    String(process.env.npm_config_location || "").trim() === "global";
}

function runBootstrap() {
  const installScript = path.join(__dirname, "install.js");
  const result = spawnSync(process.execPath, [installScript], {
    stdio: "inherit",
    env: process.env
  });
  if (typeof result.status === "number") {
    return result.status;
  }
  return 1;
}

if (isTrue(process.env.CLAWPANEL_SKIP_POSTINSTALL)) {
  process.exit(0);
}

if (!isGlobalInstall()) {
  process.exit(0);
}

const code = runBootstrap();
if (code !== 0) {
  console.warn("[WARN] postinstall bootstrap failed. You can run: clawpanel install");
}
process.exit(0);
