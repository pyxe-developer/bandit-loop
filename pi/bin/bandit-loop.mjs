#!/usr/bin/env node

import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const scripts = new Set([
  "dashboard",
  "delivery-operation",
  "evidence-ledger",
  "orchestrate-assisted",
  "review-package",
  "route-card",
  "verify-stage",
]);

const [, , scriptName, ...args] = process.argv;
if (!scriptName || !scripts.has(scriptName)) {
  console.error(`Usage: bandit-loop <${[...scripts].join("|")}> [args...]`);
  process.exitCode = 2;
} else {
  const child = spawn(resolve(packageRoot, "scripts", scriptName), args, {
    cwd: packageRoot,
    stdio: ["pipe", "inherit", "inherit"],
  });

  process.stdin.pipe(child.stdin);
  child.on("error", (error) => {
    console.error(`bandit-loop: ${error.message}`);
    process.exitCode = 1;
  });
  child.on("close", (code, signal) => {
    process.exitCode = signal ? 1 : code ?? 1;
  });
}
