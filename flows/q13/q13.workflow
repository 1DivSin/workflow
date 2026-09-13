-- Q-13 two serial Human checkpoints
const document: Artifact;
const first_answer: Artifact;
const second_answer: Artifact;
const first: Step;
const second: Step;
const human_one: Human, Executor;
const human_two: Human, Executor;
workflow q13 {
 input_workflow(q13) == [document];
 consumes(first) == [document];
 produces(first) == [first_answer];
 consumes(second) == [document, first_answer];
 produces(second) == [second_answer];
 output_workflow(q13) == [second_answer];
 step_executor(first) == human_one;
 step_executor(second) == human_two;
 step_name(first) == "Choose layer";
 step_instruction(first) == "Ask exactly: 优先评审哪一层？ options: A shared, B api, C rawdata, D onto. Return a choice request.";
 step_name(second) == "Approve review";
 step_instruction(second) == "Ask exactly: 是否接受这份边界评审作为后续依据？ options: 接受, 退回补证据. Return an approval request.";
}
