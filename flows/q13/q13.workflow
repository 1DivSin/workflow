-- Q-13 two serial Human checkpoints with one Program extraction
const document: Artifact;
const extracted: Artifact;
const first_answer: Artifact;
const second_answer: Artifact;
const extract: Step;
const first: Step;
const second: Step;
const extractor: Program, Executor;
const human_one: Human, Executor;
const human_two: Human, Executor;
workflow q13 {
 input_workflow(q13) == [document];
 consumes(extract) == [document];
 produces(extract) == [extracted];
 consumes(first) == [extracted];
 produces(first) == [first_answer];
 consumes(second) == [extracted, first_answer];
 produces(second) == [second_answer];
 output_workflow(q13) == [second_answer];
 step_executor(extract) == extractor;
 step_executor(first) == human_one;
 step_executor(second) == human_two;
 program_path(extractor) == "./flows/q13/extract.py";
 step_name(extract) == "Extract headings";
 step_instruction(extract) == "Extract the four architecture layer headings once and preserve the result.";
 step_name(first) == "Choose layer";
 step_instruction(first) == "Ask exactly: 优先评审哪一层？ options: A shared, B api, C rawdata, D onto. Return a choice request.";
 step_name(second) == "Approve review";
 step_instruction(second) == "Ask exactly: 是否接受这份边界评审作为后续依据？ options: 接受, 退回补证据. Return an approval request.";
}
