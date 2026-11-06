import hashlib
import os
import sys

import boto3
from botocore.config import Config

version = sys.argv[1]
src = os.path.join("artifacts", version)
endpoint = os.environ.get("S3_ENDPOINT", "http://localhost:8333")

s3 = boto3.client(
    "s3",
    endpoint_url=endpoint,
    region_name="us-east-1",
    config=Config(
        s3={"addressing_style": "path"},
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    ),
)

files = sorted(f for f in os.listdir(src) if f != "model.sha256")
lines = []
for name in files:
    h = hashlib.sha256()
    with open(os.path.join(src, name), "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    lines.append("%s  %s\n" % (h.hexdigest(), name))

with open(os.path.join(src, "model.sha256"), "w", newline="\n") as f:
    f.writelines(lines)

for name in files + ["model.sha256"]:
    key = "%s/%s" % (version, name)
    s3.upload_file(os.path.join(src, name), "models", key)
    print("uploaded models/" + key, flush=True)

print()
print("bucket contents:")
for obj in s3.list_objects_v2(Bucket="models", Prefix=version + "/").get("Contents", []):
    print("  %s  %d bytes" % (obj["Key"], obj["Size"]))
print()
print("model.sha256:")
print("".join(lines))
