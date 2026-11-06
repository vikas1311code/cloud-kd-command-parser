import hashlib
import os
import sys

import boto3
from botocore.config import Config

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ.get("S3_ENDPOINT", "http://localhost:8333"),
    region_name="us-east-1",
    config=Config(
        s3={"addressing_style": "path"},
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    ),
)

body = s3.get_object(Bucket="datasets", Key="v1/train.jsonl")["Body"].read()
expected = s3.get_object(Bucket="datasets", Key="v1/train.sha256")["Body"].read().decode().split()[0]
actual = hashlib.sha256(body).hexdigest()
print("expected:", expected)
print("actual:  ", actual)
if actual != expected:
    sys.exit("CHECKSUM MISMATCH")
os.makedirs("data", exist_ok=True)
with open("data/train.jsonl", "wb") as f:
    f.write(body)
print("checksum OK, records:", body.count(b"\n"))
