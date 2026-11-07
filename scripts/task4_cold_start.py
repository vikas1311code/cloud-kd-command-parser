import datetime
import json
import statistics
import subprocess
import time

LOG = "results/task4_cold_start.txt"
lines = []


def log(msg):
    line = "%s  %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    lines.append(line)
    with open(LOG, "w", encoding="utf-8", errors="replace") as f:
        f.write("\n".join(lines) + "\n")


def run_out(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        return "ERR " + repr(e)


def pods():
    out = run_out(["kubectl", "get", "pods", "-n", "app", "-l", "app=kd-parser", "-o", "json"])
    try:
        return json.loads(out)["items"]
    except Exception:
        return []


def ts(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def ready_info(it):
    for c in it["status"].get("conditions", []):
        if c["type"] == "Ready" and c["status"] == "True":
            return ts(c["lastTransitionTime"])
    return None


cur = [p for p in pods() if not p["metadata"].get("deletionTimestamp")]
if len(cur) != 2 or any(ready_info(p) is None for p in cur):
    raise SystemExit("need exactly 2 ready pods first. Not starting.")

run_times = []
for n in range(1, 4):
    old = {p["metadata"]["name"] for p in pods()}
    log("run %d: deleting all pods %s" % (n, sorted(old)))
    log(run_out(["kubectl", "delete", "pod", "-n", "app", "-l", "app=kd-parser", "--wait=false"]))
    t0 = time.time()
    new = []
    while time.time() - t0 < 300:
        items = [p for p in pods()
                 if not p["metadata"].get("deletionTimestamp") and p["metadata"]["name"] not in old]
        if len(items) == 2 and all(ready_info(p) is not None for p in items):
            new = items
            break
        time.sleep(2)
    if not new:
        log("run %d: NOT ready within 300 s" % n)
        raise SystemExit(1)
    per_pod = []
    with open("results/cold_start_run%d_logs.txt" % n, "w", encoding="utf-8", errors="replace") as lf:
        for p in new:
            name = p["metadata"]["name"]
            created = ts(p["metadata"]["creationTimestamp"])
            secs = (ready_info(p) - created).total_seconds()
            per_pod.append(secs)
            log("run %d: pod %s created %s, Ready after %.0f s" % (n, name, created.strftime("%H:%M:%S"), secs))
            text = run_out(["kubectl", "logs", name, "-n", "app"])
            keep = [l for l in text.splitlines() if "checksums verified" in l or "model load" in l or "Started server" in l]
            lf.write("== %s ==\n%s\n" % (name, "\n".join(keep)))
    run_time = max(per_pod)
    run_times.append(run_time)
    log("run %d: all replicas Ready after %.0f s (slowest pod)" % (n, run_time))
    time.sleep(5)

log("run values (slowest pod per run): %s" % ", ".join("%.0f s" % t for t in run_times))
log("MEDIAN of 3 runs: %.0f s" % statistics.median(run_times))
