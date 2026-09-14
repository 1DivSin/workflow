-- Q-08: Agent TerminalStep strict Boolean contract and one repair.

const state: Artifact;
const done: BoolArtifact;

const advance: Step;
const terminal: TerminalStep;

const advance_program: Program, Executor;
const terminal_agent: Agent, Executor;

workflow q08 {
  input_workflow(q08) == [state];
  consumes(advance) == [state];
  produces(advance) == [state];
  consumes(terminal) == [state];
  produces(terminal) == [done];
  output_workflow(q08) == [state];

  step_executor(advance) == advance_program;
  step_executor(terminal) == terminal_agent;
  program_path(advance_program) == "./flows/q27/advance_state.py";

  step_name(advance) == "Advance State";
  step_instruction(advance) == "Read state and emit the next state as the sole stdout value. Preserve JSON and increment epoch.";

  step_name(terminal) == "Strict Boolean Terminal";
  step_instruction(terminal) == "This is Q-08. You must exercise one validation repair. On your first submission, deliberately submit the exact JSON string value \"true\" for done (type string), so the runtime rejects it as a TerminalStep output contract error. Do not skip the failed submission and do not change the terminal condition. After the runtime repair prompt, submit the exact JSON Boolean true for done (type boolean). Submit exactly once per attempt. The final report must preserve the raw first and repaired values, parsed types, diagnostic kind, repair count, epoch count, and final state.";
}