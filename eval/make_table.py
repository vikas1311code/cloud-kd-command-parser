import json
rows = [("Teacher (phi3.5)", "teacher"), ("Untrained Pythia-70M", "untrained"),
        ("Student v1", "student_v1"), ("Student v2", "student_v2")]
keys = ["json_validity", "intent_accuracy", "date_accuracy", "time_accuracy", "place_accuracy", "full_frame"]
lines = ["| Model | " + " | ".join(keys) + " |", "|---|" + "---|" * len(keys)]
for label, name in rows:
    d = json.load(open("results/score_%s.json" % name))
    lines.append("| %s | " % label + " | ".join("%.1f" % d[k] for k in keys) + " |")
open("results/task2_scores.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))
