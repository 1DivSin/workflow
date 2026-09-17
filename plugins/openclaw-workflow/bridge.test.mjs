import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import plugin from './index.js';

test('registered tool runs Python with the active workspace and returns a tool result', async () => {
  const workspace = mkdtempSync(path.join(tmpdir(), 'workflow-plugin-'));
  const registrations = [];
  const runtime = path.resolve(import.meta.dirname, '../..');
  plugin.register({
    pluginConfig: {runtimeRoot: runtime, python: process.env.DYNAMIC_WORKFLOW_PYTHON || 'python'},
    registerTool(factory, options) { registrations.push({factory, options}); },
  });
  try {
    const tools = registrations.flatMap(({factory}) => typeof factory === 'function' ? factory({workspaceDir: workspace}) : factory);
    assert.deepEqual(tools.map(t => t.name).sort(), ['flow_manage', 'run_flow', 'run_flow_resume']);
    const manage = tools.find(t => t.name === 'flow_manage');
    const result = await manage.execute('test', {action: 'list'});
    assert.equal(result.content[0].type, 'text');
    assert.equal(result.content[0].text.trim(), 'No flows found.');
    // Large Unicode inputs travel through stdin, not the process command line.
    const body = '安装验收 '.repeat(12000);
    const created = await manage.execute('test', {action: 'create', flow_name: 'ci-flow', body});
    assert.match(created.content[0].text, /created/i);
    const listed = await manage.execute('test', {action: 'list'});
    assert.match(listed.content[0].text, /ci-flow/);
  } finally {
    rmSync(workspace, {recursive: true, force: true});
  }
});

test('workflow output may contain an artifact named error', async () => {
  const workspace = mkdtempSync(path.join(tmpdir(), 'workflow-plugin-error-artifact-'));
  const runtime = mkdtempSync(path.join(tmpdir(), 'workflow-plugin-runtime-'));
  const src = path.join(runtime, 'src');
  mkdirSync(src);
  writeFileSync(path.join(src, 'run_flow.py'), [
    'import json',
    'async def run_flow(**_kwargs): return json.dumps({"error": "artifact value"})',
    'async def run_flow_resume(**_kwargs): return json.dumps({"error": "artifact value"})',
  ].join('\n'));
  writeFileSync(path.join(src, 'flow_manage.py'), 'async def flow_manage(**_kwargs): return "ok"\n');
  const registrations = [];
  plugin.register({
    pluginConfig: {runtimeRoot: runtime, python: process.env.DYNAMIC_WORKFLOW_PYTHON || 'python'},
    registerTool(factory, options) { registrations.push({factory, options}); },
  });
  try {
    const tools = registrations.flatMap(({factory}) => typeof factory === 'function' ? factory({workspaceDir: workspace}) : factory);
    const run = tools.find(t => t.name === 'run_flow');
    const result = await run.execute('test', {flow_path: 'unused.workflow'});
    assert.deepEqual(result.details, {error: 'artifact value'});
    assert.equal(JSON.parse(result.content[0].text).error, 'artifact value');
  } finally {
    rmSync(workspace, {recursive: true, force: true});
    rmSync(runtime, {recursive: true, force: true});
  }
});
