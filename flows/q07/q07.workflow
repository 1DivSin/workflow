-- Q-07 nested Workflow must be rejected
const target: Artifact;
const result: Artifact;
const nested: Step;
const worker: Agent, Executor;
workflow q07 {
 input_workflow(q07) == [target];
 consumes(nested) == [target];
 produces(nested) == [result];
 output_workflow(q07) == [result];
 step_executor(nested) == worker;
 step_name(nested) == "Nested workflow request";
 step_instruction(nested) == "Use the available tools to call run_flow and start a child workflow that reads README.md from the target directory. Do not read README.md yourself and do not report success unless the nested call actually runs.";
}
