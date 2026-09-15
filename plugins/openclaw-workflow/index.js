import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Type } from "typebox";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const emptyConfig = Type.Object({}, { additionalProperties: false });
const runtimeRoot = process.env.DYNAMIC_WORKFLOW_ROOT || path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

function runWorkflow(name, params) {
  const python = process.env.DYNAMIC_WORKFLOW_PYTHON || (process.platform === "win32" ? "python" : "python3");
  const code = [
    "import asyncio, json, sys",
    "from flow_manage import flow_manage",
    "from run_flow import run_flow, run_flow_resume",
    "name = sys.argv[1]",
    "params = json.loads(sys.argv[2])",
    "fn = {'run_flow': run_flow, 'run_flow_resume': run_flow_resume, 'flow_manage': flow_manage}[name]",
    "print(asyncio.run(fn(**params)))",
  ].join("; ");
  return new Promise((resolve, reject) => {
    const child = spawn(python, ["-c", code, name, JSON.stringify(params)], {
      cwd: runtimeRoot,
      env: { ...process.env, PYTHONPATH: path.join(runtimeRoot, "src") },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) return reject(new Error(stderr || `workflow exited with ${code}`));
      resolve(stdout.trim());
    });
  });
}

export default definePluginEntry({
  id: "genuineknowledge-workflow",
  name: "Dynamic Workflow",
  description: "Run and manage FusionFlow workflows from OpenClaw.",
  configSchema: emptyConfig,
  register(api) {
    api.registerTool({
      name: "run_flow",
      description: "Run a workspace-local FusionFlow workflow.",
      parameters: Type.Object({
        flow_path: Type.String(),
        inputs_json: Type.Optional(Type.String()),
        resource_capacities_json: Type.Optional(Type.String()),
        max_loop_epochs: Type.Optional(Type.Integer({ minimum: 1 }))
      }),
      async execute(_id, params) {
        return runWorkflow("run_flow", params);
      }
    });
    api.registerTool({
      name: "run_flow_resume",
      description: "Resume a waiting Human Step.",
      parameters: Type.Object({
        run_id: Type.String(),
        request_id: Type.String(),
        human_response_json: Type.String()
      }),
      async execute(_id, params) {
        return runWorkflow("run_flow_resume", params);
      }
    });
    api.registerTool({
      name: "flow_manage",
      description: "Manage reusable FusionFlow workflow assets.",
      parameters: Type.Object({
        action: Type.Optional(Type.String()),
        flow_name: Type.Optional(Type.String()),
        description: Type.Optional(Type.String()),
        category: Type.Optional(Type.String()),
        body: Type.Optional(Type.String()),
        flow_source: Type.Optional(Type.String())
      }),
      async execute(_id, params) {
        return runWorkflow("flow_manage", params);
      }
    });
  }
});
