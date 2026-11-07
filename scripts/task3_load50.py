import json
import re
import statistics
import subprocess
import threading
import time
import urllib.request

URL = "http://localhost:8002"
CONTAINER = "kd-limit"
N = 50
UNITS = {"B": 1 / 1048576, "KiB": 1 / 1024, "MiB": 1.0, "GiB": 1024.0}
lines = []


def log(msg):
    print(msg, flush=True)
    lines.append(msg)


def to_mib(s):
    m = re.match(r"([\d.]+)\s*([A-Za-z]+)", s.strip())
    return float(m.group(1)) * UNITS.get(m.group(2), 0.0)


samples = []
stop = threading.Event()


def sampler():
    while not stop.is_set():
        r = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", CONTAINER],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and "/" in r.stdout:
            samples.append(to_mib(r.stdout.split("/")[0]))


th = threading.Thread(target=sampler, daemon=True)
th.start()

t_start = time.time()
while True:
    try:
        with urllib.request.urlopen(URL + "/readyz", timeout=5) as r:
            if r.status == 200:
                break
    except Exception:
        pass
    if time.time() - t_start > 300:
        raise SystemExit("service never became ready")
    time.sleep(2)
log("ready after %.0f s" % (time.time() - t_start))

with open("data/validation.jsonl", encoding="utf-8") as f:
    texts = [json.loads(l)["text"] for l in f if l.strip()][:N]

ok = 0
lat = []
for i, t in enumerate(texts, 1):
    req = urllib.request.Request(
        URL + "/parse",
        data=json.dumps({"text": t}).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            code = r.status
            obj = json.loads(r.read())
    except Exception as e:
        code, obj = repr(e), None
    dt = time.time() - t0
    lat.append(dt)
    good = code == 200 and isinstance(obj, dict) and set(obj) == {"intent", "date", "time", "place"}
    ok += 1 if good else 0
    log("request %02d status %s ok=%s %.2fs" % (i, code, good, dt))

stop.set()
th.join(timeout=10)

log("")
log("requests ok: %d / %d" % (ok, N))
lat_sorted = sorted(lat)
log("latency median %.2fs, p95 %.2fs, max %.2fs" % (
    statistics.median(lat), lat_sorted[int(0.95 * len(lat_sorted)) - 1], max(lat)))
if samples:
    log("docker stats samples: %d, peak memory seen %.1f MiB (limit 1024 MiB)" % (len(samples), max(samples)))
insp = subprocess.run(
    ["docker", "inspect", "-f", "OOMKilled={{.State.OOMKilled}} Status={{.State.Status}} Restarts={{.RestartCount}}", CONTAINER],
    capture_output=True, text=True)
log("container state: " + insp.stdout.strip())
pk = subprocess.run(["docker", "exec", CONTAINER, "cat", "/sys/fs/cgroup/memory.peak"], capture_output=True, text=True)
if pk.returncode == 0 and pk.stdout.strip().isdigit():
    log("cgroup memory.peak: %.1f MiB" % (int(pk.stdout.strip()) / 1048576))
else:
    log("cgroup memory.peak not available")

with open("results/task3_load50.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
