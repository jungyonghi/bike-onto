// Timestamp: 2026-05-19 14:50:00

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

interface BikeRunResult {
	code: number;
	stdout: string;
	stderr: string;
	command: string[];
}

const MAX_OUTPUT_CHARS = 24_000;

function clipOutput(value: string): string {
	if (value.length <= MAX_OUTPUT_CHARS) return value;
	return value.slice(0, MAX_OUTPUT_CHARS) + "\n... [truncated by Bike Onto pi extension]";
}

function bikeCommand(cwd: string): { command: string; argsPrefix: string[] } {
	const bike = join(cwd, "bike");
	const bikePs1 = join(cwd, "bike.ps1");
	const cliRelativePath = "tools/scripts/rag/general_rag_cli.py";
	const cli = join(cwd, ...cliRelativePath.split("/"));
	if (process.platform === "win32" && existsSync(bikePs1)) {
		return { command: "powershell.exe", argsPrefix: ["-ExecutionPolicy", "Bypass", "-File", bikePs1] };
	}
	if (existsSync(bike)) {
		return { command: bike, argsPrefix: [] };
	}
	return { command: process.env.PYTHON || "python3", argsPrefix: [cli] };
}

function runBike(ctx: ExtensionContext, args: string[], options: { input?: string; env?: NodeJS.ProcessEnv } = {}): Promise<BikeRunResult> {
	const resolved = bikeCommand(ctx.cwd);
	const fullArgs = [...resolved.argsPrefix, ...args];
	return new Promise((resolve, reject) => {
		const child = spawn(resolved.command, fullArgs, {
			cwd: ctx.cwd,
			env: { ...process.env, ...(options.env || {}) },
			stdio: [options.input ? "pipe" : "ignore", "pipe", "pipe"],
		});
		let stdout = "";
		let stderr = "";
		child.stdout.on("data", (chunk) => {
			stdout += chunk.toString();
		});
		child.stderr.on("data", (chunk) => {
			stderr += chunk.toString();
		});
		child.on("error", reject);
		child.on("close", (code) => {
			resolve({
				code: code ?? 0,
				stdout: clipOutput(stdout),
				stderr: clipOutput(stderr),
				command: [resolved.command, ...fullArgs],
			});
		});
		if (options.input && child.stdin) {
			child.stdin.write(options.input);
			child.stdin.end();
		}
	});
}

function toolText(result: BikeRunResult): string {
	const body = result.stdout.trim() || result.stderr.trim() || "(no output)";
	return result.code === 0 ? body : `Bike Onto command failed (${result.code})\n\n${body}`;
}

function jsonFromStdout(result: BikeRunResult): unknown {
	try {
		return JSON.parse(result.stdout);
	} catch {
		return undefined;
	}
}

function registerCommands(pi: ExtensionAPI) {
	pi.registerCommand("bike-setup", {
		description: "Run Bike Onto first-run setup wizard for this project",
		handler: async (_args, ctx) => {
			if (!ctx.hasUI) {
				const result = await runBike(ctx, ["setup", "--yes", "--offline"]);
				ctx.ui.notify(toolText(result), result.code === 0 ? "info" : "error");
				return;
			}
			const mode = await ctx.ui.select("Bike Onto setup mode", ["offline", "live"]);
			if (!mode) return;
			const args = ["setup", "--yes", mode === "live" ? "--live" : "--offline"];
			if (mode === "live" && !process.env.OPENAI_API_KEY) {
				ctx.ui.notify("OPENAI_API_KEY is not set. Set it before launching pi, then run /bike-setup again.", "warning");
				return;
			}
			const result = await runBike(ctx, args);
			ctx.ui.notify(toolText(result), result.code === 0 ? "info" : "error");
		},
	});

	pi.registerCommand("bike-status", {
		description: "Show Bike Onto local setup status without printing secrets",
		handler: async (_args, ctx) => {
			const result = await runBike(ctx, ["status"]);
			ctx.ui.notify(toolText(result), result.code === 0 ? "info" : "error");
		},
	});

	pi.registerCommand("bike-tools", {
		description: "List Bike Onto extension tools",
		handler: async (_args, ctx) => {
			ctx.ui.notify(
				[
					"Bike Onto tools:",
					"- bike_rag_answer: answer a question with inspection payload",
					"- bike_visual_inspect: create single-answer Visual Inspector HTML",
					"- bike_ontology_map: create NODEPROMPT-inspired ontology map",
					"- bike_wiki_export: export evaluation results as Obsidian wiki notes",
					"Config/secrets live outside repo under ~/.bike-onto",
				].join("\n"),
				"info",
			);
		},
	});
}

function registerTools(pi: ExtensionAPI) {
	pi.registerTool({
		name: "bike_rag_answer",
		label: "Bike Onto RAG Answer",
		description: "Ask Bike Onto one RAG inspection question and return the grounded answer payload.",
		promptSnippet: "Use bike_rag_answer when the user asks a domain/RAG question that should be grounded with Bike Onto evidence.",
		promptGuidelines: [
			"Prefer this tool over ad-hoc guessing for Bike Onto or RAG inspection questions.",
			"Summarize the answer, review gate, and key evidence after the tool returns.",
		],
		parameters: Type.Object({
			question: Type.String({ description: "User question to ask Bike Onto" }),
			category: Type.Optional(Type.String({ description: "Optional answer policy/category hint" })),
			verbose: Type.Optional(Type.Boolean({ description: "Return verbose terminal sections in addition to JSON details", default: false })),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const args = ["ask", params.question, "--json"];
			if (params.category) args.push("--category", params.category);
			const result = await runBike(ctx, args);
			const details = jsonFromStdout(result) ?? { stdout: result.stdout, stderr: result.stderr };
			if (params.verbose) {
				const textResult = await runBike(ctx, ["ask", params.question, "--verbose"]);
				return {
					content: [{ type: "text", text: toolText(textResult) }],
					details: { payload: details, command: result.command, verboseCommand: textResult.command },
				};
			}
			return {
				content: [{ type: "text", text: toolText(result) }],
				details: { payload: details, command: result.command },
			};
		},
	});

	pi.registerTool({
		name: "bike_visual_inspect",
		label: "Bike Onto Visual Inspector",
		description: "Generate a single-answer RAG Visual Inspector HTML artifact for a question.",
		parameters: Type.Object({
			question: Type.String({ description: "Question to answer and inspect" }),
			output: Type.Optional(Type.String({ description: "Output HTML path", default: "artifacts/pi_extension/visual_inspector.html" })),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const output = params.output || `artifacts/pi_extension/visual_${Date.now()}.html`;
			const graphJson = output.replace(/\.html?$/i, ".visual_graph.json");
			const result = await runBike(ctx, ["visual", "--question", params.question, "--output", output, "--graph-json", graphJson, "--json"]);
			return {
				content: [{ type: "text", text: toolText(result) }],
				details: { payload: jsonFromStdout(result), output, graphJson, command: result.command },
			};
		},
	});

	pi.registerTool({
		name: "bike_ontology_map",
		label: "Bike Onto Ontology Map",
		description: "Generate a NODEPROMPT-inspired ontology/evidence graph image artifact.",
		parameters: Type.Object({
			output: Type.Optional(Type.String({ description: "Output PNG path", default: "artifacts/pi_extension/ontology_map.png" })),
			preview: Type.Optional(Type.String({ description: "Optional preview JPG path" })),
			graphJson: Type.Optional(Type.String({ description: "Optional graph JSON path" })),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const output = params.output || "artifacts/pi_extension/ontology_map.png";
			const preview = params.preview || output.replace(/\.png$/i, "_preview.jpg");
			const graphJson = params.graphJson || output.replace(/\.png$/i, ".json");
			const result = await runBike(ctx, ["ontology-map", "--output", output, "--preview", preview, "--graph-json", graphJson, "--json"]);
			return {
				content: [{ type: "text", text: toolText(result) }],
				details: { payload: jsonFromStdout(result), output, preview, graphJson, command: result.command },
			};
		},
	});

	pi.registerTool({
		name: "bike_wiki_export",
		label: "Bike Onto Wiki Export",
		description: "Export RAG evaluation results into an Obsidian ontology-like wiki vault.",
		parameters: Type.Object({
			resultsJsonl: Type.String({ description: "Evaluation results JSONL path" }),
			graphJson: Type.Optional(Type.String({ description: "Optional VisualGraphPayload JSON path" })),
			vault: Type.String({ description: "Output Obsidian vault path" }),
			runId: Type.Optional(Type.String({ description: "Run identifier", default: "pi_extension_run" })),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			if (ctx.hasUI) {
				const ok = await ctx.ui.confirm("Bike Onto wiki export", `Write Obsidian wiki notes to ${params.vault}?`);
				if (!ok) {
					return { content: [{ type: "text", text: "Wiki export cancelled by user." }], details: { cancelled: true } };
				}
			}
			const args = ["wiki-export", "--results-jsonl", params.resultsJsonl, "--vault", params.vault, "--run-id", params.runId || "pi_extension_run", "--json"];
			if (params.graphJson) args.push("--graph-json", params.graphJson);
			const result = await runBike(ctx, args);
			return {
				content: [{ type: "text", text: toolText(result) }],
				details: { payload: jsonFromStdout(result), command: result.command },
			};
		},
	});
}

export default function bikeOntoExtension(pi: ExtensionAPI) {
	registerCommands(pi);
	registerTools(pi);

	pi.on("session_start", async (_event, ctx) => {
		ctx.ui.setStatus("bike-onto", "Bike Onto extension loaded");
	});
}
