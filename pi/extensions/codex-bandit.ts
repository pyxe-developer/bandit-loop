import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const requestParameters = Type.Object({
	request: Type.Record(Type.String(), Type.Unknown()),
});

const toolScripts = {
	codex_bandit_dashboard: "dashboard",
	codex_bandit_delivery_operation: "delivery-operation",
	codex_bandit_evidence_ledger: "evidence-ledger",
	codex_bandit_orchestrate: "orchestrate-assisted",
	codex_bandit_review_package: "review-package",
	codex_bandit_route_card: "route-card",
	codex_bandit_verify_stage: "verify-stage",
} as const;

type ToolName = keyof typeof toolScripts;

function runScript(scriptName: string, request: Record<string, unknown>): Promise<{
	stdout: string;
	stderr: string;
	exitCode: number;
}> {
	return new Promise((resolveResult, reject) => {
		const child = spawn(resolve(packageRoot, "scripts", scriptName), [], {
			cwd: packageRoot,
			stdio: ["pipe", "pipe", "pipe"],
		});
		let stdout = "";
		let stderr = "";
		child.stdout.on("data", (chunk) => {
			stdout += chunk;
		});
		child.stderr.on("data", (chunk) => {
			stderr += chunk;
		});
		child.on("error", reject);
		child.on("close", (code) => resolveResult({ stdout, stderr, exitCode: code ?? 1 }));
		child.stdin.end(JSON.stringify(request));
	});
}

export default function (pi: ExtensionAPI) {
	for (const [name, scriptName] of Object.entries(toolScripts) as [ToolName, string][]) {
		pi.registerTool({
			name,
			label: name,
			description: `Delegate to the Codex Bandit ${scriptName} entry point.`,
			parameters: requestParameters,
			async execute(_toolCallId, params) {
				const result = await runScript(scriptName, params.request);
				const text = result.stdout || result.stderr || `exit code ${result.exitCode}`;
				return {
					content: [{ type: "text", text }],
					details: {
						script: scriptName,
						exit_code: result.exitCode,
						stderr: result.stderr,
					},
				};
			},
		});
	}
}
