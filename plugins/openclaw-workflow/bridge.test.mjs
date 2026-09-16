import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
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
