#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

function isFalse(value) {
  const text = String(value || "").trim().toLowerCase();
  return text === "0" || text === "false" || text === "no" || text === "off";
}

function printHelp() {
  console.log("ClawPanel npm bridge");
  console.log("");
  console.log("Usage:");
  console.log("  clawpanel install [install.sh args]   # run installer explicitly");
  console.log("  clawpanel tui                          # start TUI");
  console.log("  clawpanel web --port 4231             # start Web UI");
  console.log("");
  console.log("Shortcuts:");
  console.log("  clawpanel-install [install.sh args]");
  console.log("  clawtui");
  console.log("");
  console.log("Env (npm bridge):");
  console.log("  CLAWPANEL_AUTO_BOOTSTRAP=0            # disable auto bootstrap");
  console.log("  CLAWPANEL_INSTALL_DIR=/path           # forwarded to install.sh");
  console.log("  CLAWPANEL_BIN_DIR=/path               # forwarded to install.sh");
  console.log("  CLAWPANEL_OPENCLAW_HOME=/path         # forwarded to install.sh");
}

function runNodeScript(scriptName, args) {
  const scriptPath = path.join(__dirname, scriptName);
  const result = spawnSync(process.execPath, [scriptPath, ...(args || [])], {
    stdio: "inherit",
    env: process.env
  });
  return typeof result.status === "number" ? result.status : 1;
}

function resolveInstalledClawpanel() {
  const seen = new Set();
  const candidates = [];

  const explicitBin = String(process.env.CLAWPANEL_BIN || "").trim();
  if (explicitBin) {
    if (explicitBin.endsWith("/clawpanel")) {
      candidates.push(explicitBin);
    } else {
      candidates.push(path.join(explicitBin, "clawpanel"));
    }
  }

  if (process.env.HOME) {
    candidates.push(path.join(process.env.HOME, ".local", "bin", "clawpanel"));
  }
  candidates.push("/usr/local/bin/clawpanel");

  let selfRealPath = "";
  try {
    selfRealPath = fs.realpathSync(process.argv[1]);
  } catch (_) {
    selfRealPath = "";
  }

  for (const item of candidates) {
    const p = String(item || "").trim();
    if (!p || seen.has(p)) {
      continue;
    }
    seen.add(p);
    if (!fs.existsSync(p)) {
      continue;
    }
    try {
      const real = fs.realpathSync(p);
      if (selfRealPath && real === selfRealPath) {
        continue;
      }
    } catch (_) {
      // ignore
    }
    return p;
  }
  return "";
}

function runInstalledClawpanel(args) {
  const target = resolveInstalledClawpanel();
  if (!target) {
    return 127;
  }
  const result = spawnSync(target, args || [], {
    stdio: "inherit",
    env: process.env
  });
  return typeof result.status === "number" ? result.status : 1;
}

function main() {
  const args = process.argv.slice(2);
  const first = String(args[0] || "").trim().toLowerCase();

  if (!first || first === "-h" || first === "--help" || first === "help") {
    printHelp();
    return 0;
  }

  if (first === "install" || first === "bootstrap") {
    return runNodeScript("install.js", args.slice(1));
  }

  let exitCode = runInstalledClawpanel(args);
  if (exitCode !== 127) {
    return exitCode;
  }

  if (isFalse(process.env.CLAWPANEL_AUTO_BOOTSTRAP)) {
    console.error("[ERROR] ClawPanel not installed yet. Run: clawpanel install");
    return 1;
  }

  console.log("[INFO] ClawPanel runtime not found, bootstrapping with install.sh...");
  exitCode = runNodeScript("install.js", []);
  if (exitCode !== 0) {
    return exitCode;
  }
  return runInstalledClawpanel(args);
}

process.exit(main());
