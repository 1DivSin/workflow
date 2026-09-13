-- Q-17 fixed eight commit foreach
const commits: Artifact;
const item: Artifact;
const report: Artifact;
const inspect: Step;
const inspector: Program, Executor;
workflow q17 {
 input_workflow(q17) == [commits];
 foreach_item(inspect, commits) == item;
 produces(inspect) == [report];
 output_workflow(q17) == [report];
 step_executor(inspect) == inspector;
 program_path(inspector) == "./flows/q17/show_item.py";
 step_name(inspect) == "Inspect commit";
 step_instruction(inspect) == "Run the exact git show command for this commit and preserve stdout.";
 max_concurrency(q17) == 8;
}
