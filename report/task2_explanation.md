# Task 2: Explanation (sequence-level vs logit-based distillation)

## (a) What sequence-level distillation trains on
The student is trained on the teacher's generated text. For each command, phi3.5 writes a JSON reply, and we fine-tune Pythia-70M with ordinary next-token cross-entropy to reproduce that reply, given "Command: <text>\nJSON:". The teacher's output string is a hard target, as if it were a label.

## (b) What logit-based distillation trains on
Logit-based distillation trains the student to match the teacher's full output probability distribution at every token position, usually by minimising KL divergence between the two distributions (often with a temperature). The student learns from how the teacher ranks all alternatives at each step, not just from the one token it chose.

## (c) Why logit-based distillation is not possible in this project
We only keep the text reply that Ollama returns for each command. We do not have the teacher's per-token probabilities. Also, phi3.5 and Pythia-70M use different tokenizers and vocabularies, so even with the teacher's logits, position i of the teacher would not line up with position i of the student, and the two distributions could not be compared token by token. Sequence-level distillation avoids both problems, because text can be re-tokenised by any tokenizer.

## (d) One real limitation of what we did
The student copies the teacher, including its mistakes, because the teacher's output is the only target. The teacher scored 50% full-frame on the 100 validation commands, and the cleaning step only removes replies that fail format checks, not replies that are valid JSON but wrong. Example: for V003 ("give me the time at washington right now") the teacher put "washington" in time instead of place, and student v1 made the same mistake.

## Supporting results (measured, 100 validation commands, tools/score.py)
| Model | json_validity | intent_accuracy | date_accuracy | time_accuracy | place_accuracy | full_frame |
|---|---|---|---|---|---|---|
| Teacher (phi3.5) | 84.0 | 76.0 | 69.0 | 77.0 | 77.0 | 50.0 |
| Untrained Pythia-70M | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Student v1 | 100.0 | 87.0 | 81.0 | 90.0 | 85.0 | 52.0 |
| Student v2 | 100.0 | 86.0 | 78.0 | 91.0 | 85.0 | 53.0 |

Training: seed 42 and 3 epochs (v1) vs seed 43 and 4 epochs (v2), 1,500 cleaned records, same other settings. Final-epoch training loss: v1 0.0440, v2 0.0235.

What changed: training took the untrained model from 0% to 100% JSON validity. The teacher's validity is 84% partly because some of its replies add explanatory text after the JSON, which breaks parsing. v1 and v2 are comparable, since one validation example equals one percentage point and the validation set is small. The students score above the teacher mainly because they were trained on filtered, valid replies, not because they understand the task better.
