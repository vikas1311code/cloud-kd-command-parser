import hashlib
import json
import os
import socket
import threading
import time
from contextlib import asynccontextmanager

import boto3
import jsonschema
import torch
from botocore.config import Config
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_URI = os.environ["MODEL_URI"]
MODEL_VERSION = os.environ["MODEL_VERSION"]
S3_ENDPOINT = os.environ["S3_ENDPOINT"]
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "64"))
FAULT_INJECT = os.environ.get("FAULT_INJECT", "0") == "1"
POD_NAME = os.environ.get("HOSTNAME") or socket.gethostname()
MODEL_DIR = "/tmp/model"

with open(os.path.join(os.path.dirname(__file__), "schema.json"), encoding="utf-8") as f:
    SCHEMA = json.load(f)["json_schema"]

torch.set_num_threads(1)

state = {"ready": False, "error": None, "failed": False}
holder = {}
infer_lock = threading.Lock()


def download_model():
    bucket, _, prefix = MODEL_URI[len("s3://"):].partition("/")
    prefix = prefix.rstrip("/") + "/"
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
    os.makedirs(MODEL_DIR, exist_ok=True)
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    keys = [o["Key"] for o in resp.get("Contents", [])]
    if not keys:
        raise RuntimeError("no objects under %s" % MODEL_URI)
    for key in keys:
        name = key[len(prefix):]
        if name:
            s3.download_file(bucket, key, os.path.join(MODEL_DIR, name))
    sums = os.path.join(MODEL_DIR, "model.sha256")
    if os.path.exists(sums):
        with open(sums, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                digest, name = line.split()
                h = hashlib.sha256()
                with open(os.path.join(MODEL_DIR, name), "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                if h.hexdigest() != digest:
                    raise RuntimeError("checksum mismatch for " + name)
        print("checksums verified", flush=True)


def load_model():
    for attempt in range(1, 9):
        try:
            download_model()
            tok = AutoTokenizer.from_pretrained(MODEL_DIR)
            tok.pad_token = tok.eos_token
            model = AutoModelForCausalLM.from_pretrained(MODEL_DIR)
            model.eval()
            holder["tok"] = tok
            holder["model"] = model
            state["error"] = None
            state["ready"] = True
            print("model loaded from %s (version %s)" % (MODEL_URI, MODEL_VERSION), flush=True)
            return
        except Exception as e:
            state["error"] = repr(e)
            print("model load failed (attempt %d/8): %s" % (attempt, repr(e)), flush=True)
            time.sleep(min(5 * attempt, 30))
    state["failed"] = True


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=load_model, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


class ParseRequest(BaseModel):
    text: str


def headers():
    return {"X-Model-Version": MODEL_VERSION, "X-Served-By": POD_NAME}


@app.get("/healthz")
def healthz():
    if state["failed"]:
        return JSONResponse({"status": "failed", "error": state["error"]}, status_code=503)
    return {"status": "alive"}


@app.get("/readyz")
def readyz():
    if state["ready"]:
        return {"status": "ready"}
    return JSONResponse({"status": "loading", "error": state["error"]}, status_code=503)


@app.post("/parse")
def parse(req: ParseRequest):
    if not state["ready"]:
        return JSONResponse({"error": "model_not_ready"}, status_code=503, headers=headers())
    tok = holder["tok"]
    model = holder["model"]
    prompt = "Command: %s\nJSON:" % req.text
    with infer_lock:
        enc = tok(prompt, return_tensors="pt")
        with torch.no_grad():
            ids = model.generate(
                **enc,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False,
                pad_token_id=tok.eos_token_id,
            )
    text = tok.decode(ids[0][enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    if FAULT_INJECT:
        text = "not json"
    try:
        obj = json.loads(text)
        jsonschema.validate(obj, SCHEMA)
    except Exception:
        return JSONResponse({"error": "invalid_model_output"}, status_code=500, headers=headers())
    return JSONResponse(obj, status_code=200, headers=headers())
