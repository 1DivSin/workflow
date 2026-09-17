import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync, existsSync } from "node:fs";

const pluginRoot = path.dirname(fileURLToPath(import.meta.url));
const string = { type: "string" };
const parameters = (properties, required = []) => ({type: "object", properties, required, additionalProperties: false});

export function decodeBridgeEnvelope(stdout) {
  const raw = stdout.trim();
  let envelope;
  try {
    envelope = JSON.parse(raw);
  } catch {
    throw new Error("Workflow bridge returned invalid JSON");
  }
  if (!envelope || typeof envelope !== "object" || typeof envelope.ok !== "boolean") {
    throw new Error("Workflow bridge returned an invalid result envelope");
  }
  if (!envelope.ok) {
    throw new Error(String(envelope.error || "Workflow bridge failed"));
  }
  const result = envelope.result;
  const text = typeof result === "string" ? result : JSON.stringify(result);
  let details = result;
  if (typeof result === "string") {
    try { details = JSON.parse(result); } catch { /* Plain-text tool result. */ }
  }
  return { content: [{ type: "text", text }], details };
}

function runWorkflow(name, params, workspace, config, signal) {
  const settingsPath = path.join(pluginRoot, "runtime.json");
  const installed = existsSync(settingsPath) ? JSON.parse(readFileSync(settingsPath, "utf8")) : {};
  const runtimeRoot = config.runtimeRoot || process.env.DYNAMIC_WORKFLOW_ROOT || installed.runtimeRoot || path.resolve(pluginRoot, "../..");
  const python = config.python || process.env.DYNAMIC_WORKFLOW_PYTHON || installed.python || (process.platform === "win32" ? "python" : "python3");
  workspace ||= config.workspace || installed.workspace;
  if (!workspace) throw new Error("OpenClaw did not supply a workflow workspace");
  const code = [
    "import asyncio, json, sys",
    "from flow_manage import flow_manage",
    "from run_flow import run_flow, run_flow_resume",
    "name = sys.argv[1]",
    "params = json.load(sys.stdin)",
    "fn = {'run_flow': run_flow, 'run_flow_resume': run_flow_resume, 'flow_manage': flow_manage}[name]",
    "try:",
    "    result = asyncio.run(fn(**params))",
    "except Exception as error:",
    "    print(json.dumps({'ok': False, 'error': f'{type(error).__name__}: {error}'}, ensure_ascii=False))",
    "else:",
    "    print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))",
  ].join("\n");
  return new Promise((resolve, reject) => {
    const child = spawn(python, ["-c", code, name], {
      cwd: workspace,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PSI_WORKFLOW_HOST: "openclaw", PSI_WORKFLOW_WORKSPACE: workspace,
        PYTHONPATH: [path.join(runtimeRoot, "src"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter) },
      stdio: ["pipe", "pipe", "pipe"],
      signal,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
      if (stdout.length > 4 * 1024 * 1024) { child.kill(); reject(new Error("Workflow output exceeded 4 MiB")); }
    });
    child.stderr.on("data", (chunk) => { stderr = (stderr + chunk).slice(-65536); });
    child.stdin.on("error", reject);
    child.stdin.end(JSON.stringify(params));
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) return reject(new Error(stderr || `workflow exited with ${code}`));
      try {
        resolve(decodeBridgeEnvelope(stdout));
      } catch (error) {
        reject(error);
      }
    });
  });
}

export default {
  id: "genuineknowledge-workflow",
  name: "Dynamic Workflow",
  description: "Run and manage FusionFlow workflows from OpenClaw.",
  register(api) {
    const config = api.pluginConfig || {};
    api.registerTool((context) => ({
      name: "run_flow",
      description: "Run a workspace-local FusionFlow workflow.",
      parameters: parameters({
        flow_path: string, inputs_json: string, resource_capacities_json: string,
        max_loop_epochs: { type: "integer", minimum: 1 }
      }, ["flow_path"]),
      async execute(_id, params, signal) {
        return runWorkflow("run_flow", params, context.workspaceDir, config, signal);
      }
    }), { name: "run_flow" });
    api.registerTool((context) => ({
      name: "run_flow_resume",
      description: "Resume a waiting Human Step.",
      parameters: parameters({run_id: string, request_id: string, human_response_json: string}, ["run_id", "request_id", "human_response_json"]),
      async execute(_id, params, signal) {
        return runWorkflow("run_flow_resume", params, context.workspaceDir, config, signal);
      }
    }), { name: "run_flow_resume" });
    api.registerTool((context) => ({
      name: "flow_manage",
      description: "Manage reusable FusionFlow workflow assets.",
      parameters: parameters({
        action: string, flow_name: string, description: string, category: string,
        body: string, flow_source: string, flow_ts: string, target: string
      }),
      async execute(_id, params, signal) {
        return runWorkflow("flow_manage", params, context.workspaceDir, config, signal);
      }
    }), { name: "flow_manage" });
  }
};
