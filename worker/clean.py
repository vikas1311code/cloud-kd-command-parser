import hashlib
import json
import os
from collections import Counter

import boto3
from botocore.config import Config

ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:8333")
OUT = os.environ.get("CLEAN_OUT", "v1")
RESULTS = os.environ.get("RESULTS_DIR", "results")
KEYS = {"intent", "date", "time", "place"}
INTENTS = {
    "alarm_set", "alarm_query", "calendar_set", "calendar_query",
    "calendar_remove", "weather_query", "datetime_query", "recommendation_events",
}

s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    region_name="us-east-1",
    config=Config(
        s3={"addressing_style": "path"},
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    ),
)


def read_lines(key):
    body = s3.get_object(Bucket="datasets", Key=key)["Body"].read().decode("utf-8")
    return [line for line in body.split("\n") if line.strip()]


def classify(rec):
    """Return the reason letter a-d if the record is bad, else None."""
    try:
        obj = json.loads(rec["teacher_raw"].strip())
    except Exception:
        return "a"
    if not isinstance(obj, dict) or set(obj.keys()) != KEYS:
        return "b"
    if not isinstance(obj["intent"], str) or obj["intent"] not in INTENTS:
        return "c"
    for slot in ("date", "time", "place"):
        value = obj[slot]
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or value not in rec["text"]:
            return "d"
    return None


def main():
    pool_ids = [json.loads(line)["id"] for line in read_lines("commands_pool.jsonl")]
    shard_keys = sorted(
        o["Key"]
        for o in s3.list_objects_v2(Bucket="datasets", Prefix="teacher/shard-").get("Contents", [])
    )
    print("shard objects:", shard_keys)

    records = []
    for key in shard_keys:
        records += [json.loads(line) for line in read_lines(key)]

    seen_ids = Counter(r["id"] for r in records)
    missing = [i for i in pool_ids if i not in seen_ids]
    repeated = [i for i, n in seen_ids.items() if n > 1]
    if missing or repeated:
        print("WARNING: coverage problem. missing ids: %d, repeated ids: %d" % (len(missing), len(repeated)))

    rejected = {"a": 0, "b": 0, "c": 0, "d": 0}
    rejected_rows = []
    valid = []
    for rec in records:
        reason = classify(rec)
        if reason:
            rejected[reason] += 1
            rejected_rows.append({"reason": reason, **rec})
        else:
            valid.append(rec)

    valid.sort(key=lambda r: r["id"])
    first_text = set()
    kept = []
    duplicates = 0
    for rec in valid:
        if rec["text"] in first_text:
            duplicates += 1
        else:
            first_text.add(rec["text"])
            kept.append(rec)

    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    sha_line = "%s  train.jsonl\n" % digest

    s3.put_object(Bucket="datasets", Key="%s/train.jsonl" % OUT, Body=body)
    s3.put_object(Bucket="datasets", Key="%s/train.sha256" % OUT, Body=sha_line.encode())

    counts = {
        "input_records": len(records),
        "rejected_a_invalid_json": rejected["a"],
        "rejected_b_wrong_keys": rejected["b"],
        "rejected_c_bad_intent": rejected["c"],
        "rejected_d_bad_slot": rejected["d"],
        "duplicates": duplicates,
        "kept": len(kept),
        "missing_ids": len(missing),
        "repeated_ids": len(repeated),
        "sha256": digest,
    }
    assert counts["input_records"] == (
        rejected["a"] + rejected["b"] + rejected["c"] + rejected["d"] + duplicates + len(kept)
    ), "counts do not add up"

    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "clean_counts.json"), "w", encoding="utf-8") as f:
        json.dump(counts, f, indent=2)
    with open(os.path.join(RESULTS, "clean_rejected.jsonl"), "w", encoding="utf-8") as f:
        for row in rejected_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    for k, v in counts.items():
        print("%-26s %s" % (k, v))
    print("wrote datasets/%s/train.jsonl and train.sha256" % OUT)


if __name__ == "__main__":
    main()
