-- Q-17 fixed eight commit foreach, ordered reduce, Human choice
const commits: Artifact;
const item: Artifact;
const report: Artifact;

const timeline: Artifact;
const choice: Artifact;
const inspect: Step;
const reduce: Step;
const choose: Step;
const inspector: Program, Executor;
const reducer: Program, Executor;
const human: Human, Executor;
workflow q17 {
 input_workflow(q17) == [commits];
 foreach_item(inspect, commits) == item;
 produces(inspect) == [report];
 produces(reduce) == [timeline];
 consumes(reduce) == [report];
 consumes(choose) == [timeline];
 produces(choose) == [choice];
 output_workflow(q17) == [choice];
 step_executor(inspect) == inspector;
 step_executor(reduce) == reducer;
 step_executor(choose) == human;
 program_path(inspector) == "./flows/q17/show_item.py";
 program_path(reducer) == "./flows/q17/reduce.py";
 step_name(inspect) == "Inspect commit";
 step_instruction(inspect) == "Run the exact git show command for this commit and preserve stdout.";
 step_name(reduce) == "Reduce timeline";
 step_instruction(reduce) == "Preserve source order and identify three highest risk transitions.";
 step_name(choose) == "Choose regression direction";
 step_instruction(choose) == "Ask: choose a regression direction. Options: 接受前三名, 优先 Session/compaction, 优先 Router/协议, 优先 Workflow/Gateway.";
 max_concurrency(q17) == 8;
}
