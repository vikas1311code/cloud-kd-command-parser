import csv
import datetime
import json
import os
import subprocess
import time
import urllib.request

HOST = "http://localhost:8081"
LOG = "results/task4_rolling_update_log.txt"
lines = []


def log(msg):
    line = "%s  %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    lines.append(line)
    with open(LOG, "w", encoding="utf-8", errors="replace") as f:
        f.write("\n".join(lines) + "\n")


def run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return "ERR " + repr(e)


def probe():
    body = json.dumps({"text": "set an alarm for seven thirty am tomorrow"}).encode()
    req = urllib.request.Request(HOST + "/parse", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("X-Model-Version"), r.headers.get("X-Served-By")
    except Exception as e:
        return repr(e), None, None


ready = run(["kubectl", "get", "deploy", "kd-parser", "-n", "app", "-o", "jsonpath={.status.readyReplicas}"])
if ready != "2":
    raise SystemExit("need exactly 2 ready replicas, found %r. Not starting." % ready)
st, ver, pod = probe()
if st != 200 or ver != "v1":
    raise SystemExit("sanity probe failed: %r %r %r" % (st, ver, pod))
log("start state: 2 ready replicas, probe -> %s %s %s" % (st, ver, pod))

env = dict(os.environ)
env["LOADTEST_HEADERS_OUT"] = "results/rolling_update_headers.json"
cf = open("results/rolling_update_console.txt", "w", encoding="utf-8")
t0 = time.time()
lp = subprocess.Popen(
    ["locust", "-f", "tools/locustfile.py", "--headless", "--users", "4", "--spawn-rate", "4",
     "--run-time", "4m", "--host", HOST, "--csv", "results/rolling_update"],
    stdout=cf, stderr=subprocess.STDOUT, env=env)
log("locust started (4 users, 4 minutes)")
time.sleep(20)
if lp.poll() is not None:
    raise SystemExit("locust ended too early, test INVALID")

log("rollout history before:\n" + run(["kubectl", "rollout", "history", "deploy/kd-parser", "-n", "app"]))
log("set env: " + run(["kubectl", "set", "env", "deploy/kd-parser", "-n", "app",
                       "MODEL_VERSION=v2", "MODEL_URI=s3://models/v2"]))
t1 = time.time()
log(run(["kubectl", "rollout", "status", "deploy/kd-parser", "-n", "app", "--timeout=300s"], timeout=320))
log("update to v2 finished after %.0f s" % (time.time() - t1))
for _ in range(4):
    log("probe after update: %s" % (probe(),))
    time.sleep(2)
time.sleep(10)

log("rollout undo: " + run(["kubectl", "rollout", "undo", "deploy/kd-parser", "-n", "app"]))
t2 = time.time()
log(run(["kubectl", "rollout", "status", "deploy/kd-parser", "-n", "app", "--timeout=300s"], timeout=320))
log("rollback finished after %.0f s" % (time.time() - t2))
for _ in range(4):
    log("probe after rollback: %s" % (probe(),))
    time.sleep(2)
log("env now (MODEL_VERSION, MODEL_URI): " + run(
    ["kubectl", "get", "deploy", "kd-parser", "-n", "app", "-o",
     "jsonpath={range .spec.template.spec.containers[0].env[0:2]}{.name}={.value} {end}"]))
log("pods:\n" + run(["kubectl", "get", "pods", "-n", "app"]))

try:
    lp.wait(timeout=300)
except Exception:
    lp.kill()
cf.close()

log("locust finished after %.0f s" % (time.time() - t0))
try:
    with open("results/rolling_update_stats.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Name"] == "Aggregated":
                n, bad = int(row["Request Count"]), int(row["Failure Count"])
                log("Locust Aggregated: %d requests, %d failures = %.3f %%" % (n, bad, 100.0 * bad / max(n, 1)))
except Exception as e:
    log("could not read stats csv: %r" % e)
try:
    log("headers: " + json.dumps(json.load(open("results/rolling_update_headers.json")), indent=1))
except Exception as e:
    log("could not read headers json: %r" % e)
