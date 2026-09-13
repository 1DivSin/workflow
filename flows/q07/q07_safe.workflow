const request: Artifact;
const result: Artifact;
const step: Step;
const worker: Agent, Executor;
workflow q07_safe {
 input_workflow(q07_safe) == [request];
 consumes(step) == [request];
 produces(step) == [result];
 output_workflow(q07_safe) == [result];
 step_executor(step) == worker;
 step_name(step) == "Nested launcher isolation";
 step_instruction(step) == "Attempt to call run_flow or run_flow_resume using available tools. Do not read files and do not claim success unless the launcher is actually available.";
}
