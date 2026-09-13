-- Q-36 real patch capture
const keol_patch: Artifact;
const psi_patch: Artifact;
const keol: Step;
const psi: Step;
const keol_program: Program, Executor;
const psi_program: Program, Executor;
workflow q36 {
  input_workflow(q36) == [];
  consumes(keol) == [];
  produces(keol) == [keol_patch];
  consumes(psi) == [];
  produces(psi) == [psi_patch];
  output_workflow(q36) == [keol_patch, psi_patch];
  step_executor(keol) == keol_program;
  step_executor(psi) == psi_program;
  program_path(keol_program) == "./flows/q36/show_keol.py";
  program_path(psi_program) == "./flows/q36/show_psi.py";
  step_name(keol) == "KEOL patch";
  step_name(psi) == "psi-agent patch";
  step_instruction(keol) == "Capture the declared git show stdout exactly.";
  step_instruction(psi) == "Capture the declared git show stdout exactly.";
}
