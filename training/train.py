import argparse
import csv
import json
import os
import platform
import random
import time

import numpy as np
import torch
import transformers
import yaml
from torch.utils.data import DataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer, get_linear_schedule_with_warmup

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def load_records(path, n):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
            if len(records) == n:
                break
    return records


def build_example(tok, rec, max_len):
    prompt = "Command: %s\nJSON:" % rec["text"]
    target = " " + rec["teacher_raw"].strip()
    p = tok(prompt)["input_ids"]
    t = tok(target)["input_ids"] + [tok.eos_token_id]
    ids = (p + t)[:max_len]
    labels = ([-100] * len(p) + t)[:max_len]
    return ids, labels


def make_collate(pad_id):
    def collate(batch):
        longest = max(len(ids) for ids, _ in batch)
        input_ids, labels, mask = [], [], []
        for ids, lab in batch:
            pad = longest - len(ids)
            input_ids.append(ids + [pad_id] * pad)
            labels.append(lab + [-100] * pad)
            mask.append([1] * len(ids) + [0] * pad)
        return torch.tensor(input_ids), torch.tensor(labels), torch.tensor(mask)
    return collate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="training/config.yaml")
    args = ap.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    subset = int(os.environ.get("SUBSET", "0") or 0)
    n = subset if subset > 0 else int(cfg["train_examples"])
    seed = int(cfg["seed"])
    seed_everything(seed)

    if subset > 0:
        out_dir = os.path.join(cfg["output_dir"], "smoke")
        loss_csv = "training/loss_smoke.csv"
    else:
        out_dir = os.path.join(cfg["output_dir"], cfg["model_version"])
        loss_csv = cfg["loss_csv"]

    tok = AutoTokenizer.from_pretrained(cfg["model_name"])
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(cfg["model_name"])

    records = load_records(cfg["train_file"], n)
    print("training on %d records, first id %s, last id %s" % (len(records), records[0]["id"], records[-1]["id"]), flush=True)
    data = [build_example(tok, r, int(cfg["max_seq_length"])) for r in records]

    gen = torch.Generator()
    gen.manual_seed(seed)
    loader = DataLoader(
        data,
        batch_size=int(cfg["batch_size"]),
        shuffle=True,
        generator=gen,
        collate_fn=make_collate(tok.pad_token_id),
    )
    epochs = int(cfg["epochs"])
    opt = torch.optim.AdamW(
        model.parameters(),
        lr=float(cfg["learning_rate"]),
        weight_decay=float(cfg["weight_decay"]),
    )
    sched = get_linear_schedule_with_warmup(opt, int(cfg["warmup_steps"]), epochs * len(loader))

    model.train()
    rows = []
    for epoch in range(1, epochs + 1):
        losses = []
        t0 = time.time()
        for step, (ids, labels, mask) in enumerate(loader, 1):
            out = model(input_ids=ids, attention_mask=mask, labels=labels)
            out.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            losses.append(out.loss.item())
            if step % 20 == 0:
                print("epoch %d step %d/%d loss %.4f" % (epoch, step, len(loader), losses[-1]), flush=True)
        mean = sum(losses) / len(losses)
        rows.append((epoch, mean))
        print("EPOCH %d mean loss %.4f (%.0fs)" % (epoch, mean, time.time() - t0), flush=True)

    os.makedirs(os.path.dirname(loss_csv) or ".", exist_ok=True)
    with open(loss_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "loss"])
        for epoch, mean in rows:
            w.writerow([epoch, "%.6f" % mean])

    os.makedirs(out_dir, exist_ok=True)
    model.save_pretrained(out_dir)
    tok.save_pretrained(out_dir)
    info = {
        "model_version": cfg["model_version"] if subset == 0 else "smoke",
        "base_model": cfg["model_name"],
        "train_examples": len(records),
        "seed": seed,
        "learning_rate": cfg["learning_rate"],
        "batch_size": cfg["batch_size"],
        "epochs": epochs,
        "max_seq_length": cfg["max_seq_length"],
        "final_epoch_loss": rows[-1][1],
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "numpy": np.__version__,
        "pyyaml": yaml.__version__,
        "trained_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(os.path.join(out_dir, "version_info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    print("saved model to", out_dir, flush=True)


if __name__ == "__main__":
    main()
