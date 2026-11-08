"""make up: build and deploy the whole system from a fresh clone.

Steps: k3d cluster -> namespaces + secrets -> SeaweedFS -> buckets -> model from
GitHub Release (checksum verified) into the bucket -> image build + import -> deploy -> smoke test.

Credentials are never stored in the repo. If the secret already exists in the cluster it is
reused, otherwise a random one is created.
Usage: python scripts/make_up.py [--versions v1 v2]
"""
import argparse
import base64
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request

CLUSTER = "cloudlab"
REPO = os.environ.get("GITHUB_REPO", "vikas1311code/cloud-kd-command-parser")
S3_PORT, APP_PORT = 18333, 18080
ENDPOINT = "http://localhost:%d" % S3_PORT
KEYS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
DL_DIR = os.path.join("tmp_results", "release_download")


def run(cmd, check=True, **kw):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check, **kw)


def out(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def need_tools():
    for t in ("docker", "k3d", "kubectl"):
        if not shutil.which(t):
            sys.exit("missing tool on PATH: " + t)


def cluster():
    names = [c["name"] for c in json.loads(out(["k3d", "cluster", "list", "-o", "json"]).stdout or "[]")]
    if CLUSTER in names:
        print("cluster exists:", CLUSTER)
        run(["k3d", "cluster", "start", CLUSTER], check=False)
    else:
        run(["k3d", "cluster", "create", "--config", "cluster/k3d.yaml"])
    run(["kubectl", "wait", "--for=condition=Ready", "node", "--all", "--timeout=180s"])
    for ns in ("data", "pipeline", "app"):
        y = out(["kubectl", "create", "ns", ns, "--dry-run=client", "-o", "yaml"]).stdout
        run(["kubectl", "apply", "-f", "-"], input=y, text=True)


def put_secret(name, ns, data):
    args = ["kubectl", "create", "secret", "generic", name, "-n", ns, "--dry-run=client", "-o", "yaml"]
    args += ["--from-literal=%s=%s" % kv for kv in data.items()]
    y = out(args).stdout
    run(["kubectl", "apply", "-f", "-"], input=y, text=True, stdout=subprocess.DEVNULL)


def credentials():
    r = out(["kubectl", "get", "secret", "seaweedfs-s3", "-n", "data", "-o", "json"])
    if r.returncode == 0:
        d = json.loads(r.stdout)["data"]
        if not all(k in d for k in KEYS):
            sys.exit("secret seaweedfs-s3 exists but has keys %s, expected %s" % (list(d), KEYS))
        creds = {k: base64.b64decode(d[k]).decode() for k in KEYS}
        print("reusing existing secret seaweedfs-s3")
    else:
        creds = {KEYS[0]: "kd" + secrets.token_hex(4), KEYS[1]: secrets.token_hex(16)}
        put_secret("seaweedfs-s3", "data", creds)
        print("created new random secret seaweedfs-s3")
    for ns in ("app", "pipeline"):
        put_secret("s3-credentials", ns, creds)
    return creds


def port_forward(ns, svc, local, remote):
    p = subprocess.Popen(["kubectl", "port-forward", "-n", ns, "svc/" + svc, "%d:%d" % (local, remote)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    return p


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def download(url, dest, size):
    curl = shutil.which("curl")
    for attempt in range(1, 9):
        have = os.path.getsize(dest) if os.path.exists(dest) else 0
        if have == size:
            return
        if have > size:
            os.remove(dest)
            have = 0
        try:
            if curl:
                subprocess.run([curl, "-sS", "-L", "-C", "-", "--retry", "3", "--retry-all-errors",
                                "--retry-delay", "3", "-o", dest, url], check=True)
            else:
                hdr = {"User-Agent": "make-up/1.0"}
                if have:
                    hdr["Range"] = "bytes=%d-" % have
                req = urllib.request.Request(url, headers=hdr)
                with urllib.request.urlopen(req, timeout=60) as r, open(dest, "ab" if have else "wb") as f:
                    if have and r.status == 200:  # server ignored Range, restart
                        f.seek(0)
                        f.truncate()
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
        except (OSError, subprocess.CalledProcessError) as e:  # network cut: resume next attempt
            print("  attempt %d interrupted: %s" % (attempt, e), flush=True)
            time.sleep(min(5 * attempt, 40))
    got = os.path.getsize(dest) if os.path.exists(dest) else 0
    if got != size:
        sys.exit("could not download %s completely (%d of %d bytes)" % (url, got, size))


def fetch_release(version):
    api = "https://api.github.com/repos/%s/releases/tags/model-%s" % (REPO, version)
    with urllib.request.urlopen(api, timeout=60) as r:
        assets = json.loads(r.read())["assets"]
    d = os.path.join(DL_DIR, version)
    os.makedirs(d, exist_ok=True)
    for a in assets:
        print("download", version, a["name"], a["size"], flush=True)
        download(a["browser_download_url"], os.path.join(d, a["name"]), a["size"])
    # verify every file against model.sha256 from the same Release
    with open(os.path.join(d, "model.sha256"), encoding="ascii") as f:
        for line in f:
            if not line.strip():
                continue
            want, name = line.split()
            if sha256(os.path.join(d, name)) != want:
                sys.exit("CHECKSUM MISMATCH for %s %s, not uploading" % (version, name))
    print("checksums OK for", version)
    return d


def upload(version, d, creds):
    import boto3
    from botocore.config import Config
    s3 = boto3.client("s3", endpoint_url=ENDPOINT, region_name="us-east-1",
                      aws_access_key_id=creds[KEYS[0]], aws_secret_access_key=creds[KEYS[1]],
                      config=Config(s3={"addressing_style": "path"},
                                    request_checksum_calculation="when_required",
                                    response_checksum_validation="when_required"))
    for name in sorted(os.listdir(d)):
        s3.upload_file(os.path.join(d, name), "models", "%s/%s" % (version, name))
        print("uploaded models/%s/%s" % (version, name), flush=True)


def buckets(creds):
    env = dict(os.environ, S3_ENDPOINT=ENDPOINT, AWS_ACCESS_KEY_ID=creds[KEYS[0]],
               AWS_SECRET_ACCESS_KEY=creds[KEYS[1]])
    for _ in range(12):
        if run([sys.executable, "scripts/setup_buckets.py"], check=False, env=env).returncode == 0:
            return
        time.sleep(5)
    sys.exit("could not create buckets")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", nargs="+", default=["v1"])
    a = ap.parse_args()
    need_tools()
    cluster()
    creds = credentials()
    run(["kubectl", "apply", "-f", "k8s/seaweedfs.yaml"])
    run(["kubectl", "-n", "data", "rollout", "status", "deploy/seaweedfs", "--timeout=300s"])
    pf = port_forward("data", "seaweedfs", S3_PORT, 8333)
    try:
        buckets(creds)
        for v in a.versions:
            upload(v, fetch_release(v), creds)
    finally:
        pf.terminate()
    run(["docker", "build", "-t", "kd-service:v1", "service"])
    run(["k3d", "image", "import", "kd-service:v1", "-c", CLUSTER])
    for f in ("deployment", "service", "ingress", "hpa"):
        run(["kubectl", "apply", "-f", "k8s/%s.yaml" % f])
    run(["kubectl", "-n", "app", "rollout", "status", "deploy/kd-parser", "--timeout=600s"])
    pf = port_forward("app", "kd-parser", APP_PORT, 80)
    try:
        base = "http://localhost:%d" % APP_PORT
        with urllib.request.urlopen(base + "/readyz", timeout=30) as r:
            print("/readyz ->", r.status, r.read().decode())
        body = json.dumps({"text": "set an alarm for seven thirty am tomorrow"}).encode()
        req = urllib.request.Request(base + "/parse", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            print("/parse  ->", r.status, r.read().decode())
    finally:
        pf.terminate()
    print("\nmake up finished. Ingress: http://localhost:8081")


if __name__ == "__main__":
    main()
