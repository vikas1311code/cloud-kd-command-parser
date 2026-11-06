import json
import os
import time
import urllib.request

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

SHARD_INDEX = int(os.environ["SHARD_INDEX"])
SHARD_COUNT = int(os.environ["SHARD_COUNT"])
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://seaweedfs.data.svc.cluster.local:8333")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.k3d.internal:11434")
MODEL = os.environ.get("TEACHER_MODEL", "phi3.5")
PROMPT_FILE = os.environ.get("PROMPT_FILE", "/config/teacher_prompt.txt")
OUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "teacher")
LIMIT = int(os.environ.get("LIMIT", "0"))
CHECKPOINT_EVERY = 20

s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    region_name="us-east-1",
    config=Config(
        s3={"addressing_style": "path"},
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    ),
)


def ask_teacher(prompt, text):
    body = {
        "model": MODEL,
        "prompt": prompt.replace("{command}", text),
        "stream": False,
        "options": {"temperature": 0, "seed": 42, "num_predict": 120},
    }
    data = json.dumps(body).encode()
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(
                OLLAMA_URL + "/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=900) as r:
                return json.loads(r.read())["response"]
        except Exception as e:
            print("teacher error (attempt %d): %s" % (attempt, e), flush=True)
            time.sleep(5 * attempt)
    raise RuntimeError("teacher failed 3 times")


def save(key, records):
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    s3.put_object(Bucket="datasets", Key=key, Body=body.encode("utf-8"))


def main():
    prompt = open(PROMPT_FILE, encoding="utf-8").read()
    raw = s3.get_object(Bucket="datasets", Key="commands_pool.jsonl")["Body"].read().decode("utf-8")
    mine = [
        json.loads(line)
        for i, line in enumerate(raw.split("\n"))
        if line.strip() and i % SHARD_COUNT == SHARD_INDEX
    ]
    if LIMIT:
        mine = mine[:LIMIT]

    key = "%s/shard-%d.jsonl" % (OUT_PREFIX, SHARD_INDEX)
    done = {}
    try:
        old = s3.get_object(Bucket="datasets", Key=key)["Body"].read().decode("utf-8")
        for line in old.split("\n"):
            if line.strip():
                rec = json.loads(line)
                done[rec["id"]] = rec
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("NoSuchKey", "404"):
            raise

    out = [done[c["id"]] for c in mine if c["id"] in done]
    todo = [c for c in mine if c["id"] not in done]
    print("shard %d of %d: %d commands, %d already done, %d to do"
          % (SHARD_INDEX, SHARD_COUNT, len(mine), len(out), len(todo)), flush=True)

    start = time.time()
    for n, c in enumerate(todo, 1):
        t = time.time()
        reply = ask_teacher(prompt, c["text"])
        out.append({"id": c["id"], "text": c["text"], "teacher_raw": reply})
        print("%s done (%d/%d) %.1fs, elapsed %.0fs" % (c["id"], n, len(todo), time.time() - t, time.time() - start), flush=True)
        if n % CHECKPOINT_EVERY == 0:
            save(key, out)
    save(key, out)
    print("DONE shard %d: %d records written to datasets/%s" % (SHARD_INDEX, len(out), key), flush=True)


if __name__ == "__main__":
    main()
