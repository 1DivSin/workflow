-- Q-27: bounded declarative feedback loop with an always-false Program terminal.

const state: Artifact;
const done: BoolArtifact;

const advance: Step;
const terminal: TerminalStep;

const advance_program: Program, Executor;
const terminal_program: Program, Executor;

workflow q27 {
  -- DATA FLOW
  input_workflow(q27) == [state];
  consumes(advance) == [state];
  produces(advance) == [state];
  consumes(terminal) == [state];
  produces(terminal) == [done];
  output_workflow(q27) == [state];

  -- EXECUTOR ASSIGNMENT
  step_executor(advance) == advance_program;
  step_executor(terminal) == terminal_program;
  program_path(advance_program) == "./flows/q27/advance_state.py";
  program_path(terminal_program) == "./flows/q27/always_false.py";

  -- STEP CONFIGURATION
  step_name(advance) == "Advance State";
  step_instruction(advance) == "Read state and emit the next state as the sole stdout value. Preserve a finite JSON value and increment the epoch field when state is an object.";
  step_name(terminal) == "Always False Terminal";
  step_instruction(terminal) == "Run the declared Program and return its strict JSON Boolean result as done. This terminal intentionally returns false on every epoch.";
}
