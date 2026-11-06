import argparse
import json
import os
import time
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="results/pred_teacher.jsonl")
ap.add_argument("--gold", default="data/validation.jsonl")
ap.add_argument("--prompt", default="prompts/teacher_prompt.txt")
ap.add_argument("--url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
ap.add_argument("--model", default="phi3.5")
args = ap.parse_args()

prompt = open(args.prompt, encoding="utf-8").read()
with open(args.gold, encoding="utf-8") as f:
    gold = [json.loads(l) for l in f if l.strip()]


def ask(text):
    body = {
        "model": args.model,
        "prompt": prompt.replace("{command}", text),
        "stream": False,
        "options": {"temperature": 0, "seed": 42, "num_predict": 120},
    }
    req = urllib.request.Request(
        args.url + "/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["response"]


os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
start = time.time()
with open(args.out, "w", encoding="utf-8") as out:
    for i, g in enumerate(gold, 1):
        reply = ask(g["text"])
        out.write(json.dumps({"id": g["id"], "prediction": reply}, ensure_ascii=False) + "\n")
        out.flush()
        print("%s done (%d/%d) elapsed %.0fs" % (g["id"], i, len(gold), time.time() - start), flush=True)
print("wrote", args.out)
