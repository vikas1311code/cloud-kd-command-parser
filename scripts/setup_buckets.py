import os
import boto3
from botocore.config import Config

endpoint = os.environ.get("S3_ENDPOINT", "http://localhost:8333")
s3 = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    region_name="us-east-1",
    config=Config(
        s3={"addressing_style": "path"},
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    ),
)

for bucket in ("datasets", "models"):
    try:
        s3.create_bucket(Bucket=bucket)
        print("created bucket:", bucket)
    except (s3.exceptions.BucketAlreadyOwnedByYou, s3.exceptions.BucketAlreadyExists):
        print("bucket already exists:", bucket)

s3.upload_file("data/commands_pool.jsonl", "datasets", "commands_pool.jsonl")
print("uploaded: datasets/commands_pool.jsonl")

print("buckets:", [b["Name"] for b in s3.list_buckets()["Buckets"]])
for obj in s3.list_objects_v2(Bucket="datasets").get("Contents", []):
    print("datasets/" + obj["Key"], obj["Size"], "bytes")

