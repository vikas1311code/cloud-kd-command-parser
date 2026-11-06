import argparse
import json
import os

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--gold", default="data/validation.jsonl")
ap.add_argument("--max_new_tokens", type=int, default=64)
args = ap.parse_args()

tok = AutoTokenizer.from_pretrained(args.model)
tok.pad_token = tok.eos_token
model = AutoModelForCausalLM.from_pretrained(args.model)
model.eval()

with open(args.gold, encoding="utf-8") as f:
    gold = [json.loads(l) for l in f if l.strip()]

os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
with open(args.out, "w", encoding="utf-8") as out:
    for i, g in enumerate(gold, 1):
        prompt = "Command: %s\nJSON:" % g["text"]
        enc = tok(prompt, return_tensors="pt")
        with torch.no_grad():
            ids = model.generate(
                **enc,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tok.eos_token_id,
            )
        text = tok.decode(ids[0][enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        out.write(json.dumps({"id": g["id"], "prediction": text}) + "\n")
        if i % 20 == 0:
            print("done %d/%d" % (i, len(gold)), flush=True)
print("wrote", args.out)
