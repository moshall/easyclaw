#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

function isTrue(value) {
  const text = String(value || "").trim().toLowerCase();
  return text === "1" || text === "true" || text === "yes" || text === "on";
}

function isFalse(value) {
  const text = String(value || "").trim().toLowerCase();
  return text === "0" || text === "false" || text === "no" || text === "off";
}

function buildEnvInstallArgs() {
  const args = [];
  const pairs = [
    ["CLAWPANEL_INSTALL_DIR", "--install-dir"],
    ["CLAWPANEL_BIN_DIR", "--bin-dir"],
    ["CLAWPANEL_OPENCLAW_HOME", "--openclaw-home"],
    ["CLAWPANEL_TARGET_USER", "--target-user"],
    ["CLAWPANEL_TARGET_HOME", "--target-home"]
  ];
  for (const [envName, flag] of pairs) {
    const value = String(process.env[envName] || "").trim();
    if (value) {
      args.push(flag, value);
    }
  }
  if (isTrue(process.env.CLAWPANEL_SKIP_PIP)) {
    args.push("--skip-pip");
  }
  if (isTrue(process.env.CLAWPANEL_NO_AUTO_DEPS) || isFalse(process.env.CLAWPANEL_AUTO_DEPS)) {
    args.push("--no-auto-deps");
  } else if (isTrue(process.env.CLAWPANEL_AUTO_DEPS)) {
    args.push("--auto-deps");
  }
  return args;
}

function runInstall(forwardArgs) {
  const repoRoot = path.resolve(__dirname, "..");
  const installScript = path.join(repoRoot, "install.sh");
  if (!fs.existsSync(installScript)) {
    console.error(`[ERROR] install.sh not found: ${installScript}`);
    return 1;
  }

  const args = [installScript, ...buildEnvInstallArgs(), ...(forwardArgs || [])];
  const result = spawnSync("bash", args, {
    stdio: "inherit",
    env: process.env
  });

  if (typeof result.status === "number") {
    return result.status;
  }
  return 1;
}

const exitCode = runInstall(process.argv.slice(2));
process.exit(exitCode);
