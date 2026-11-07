import csv
import datetime
import json
import os
import subprocess
import time
import urllib.request

HOST = "http://localhost:8081"
LOG = "results/task4_pod_delete_log.txt"
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


def pods_state():
    out = run_out(["kubectl", "get", "pods", "-n", "app", "-l", "app=kd-parser", "-o", "json"])
    try:
        items = json.loads(out)["items"]
    except Exception:
        return None
    names, ready = [], 0
    for it in items:
        if it["metadata"].get("deletionTimestamp"):
            continue
        conds = {c["type"]: c["status"] for c in it["status"].get("conditions", [])}
        names.append(it["metadata"]["name"])
        if conds.get("Ready") == "True":
            ready += 1
    return ready, len(names), names


def probe():
    body = json.dumps({"text": "set an alarm for seven thirty am tomorrow"}).encode()
    req = urllib.request.Request(HOST + "/parse", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("X-Model-Version"), r.headers.get("X-Served-By")
    except Exception as e:
        return repr(e), None, None


st = pods_state()
if not st or st[0] != 2 or st[1] != 2:
    raise SystemExit("need exactly 2 ready pods, found %r. Not starting." % (st,))
s, v, p = probe()
if s != 200:
    raise SystemExit("sanity probe failed: %r" % ((s, v, p),))
log("start: 2 ready pods %s, probe -> %s %s %s" % (st[2], s, v, p))

env = dict(os.environ)
env["LOADTEST_HEADERS_OUT"] = "results/pod_delete_headers.json"
cf = open("results/pod_delete_console.txt", "w", encoding="utf-8")
t0 = time.time()
lp = subprocess.Popen(
    ["locust", "-f", "tools/locustfile.py", "--headless", "--users", "4", "--spawn-rate", "4",
     "--run-time", "2m", "--host", HOST, "--csv", "results/pod_delete"],
    stdout=cf, stderr=subprocess.STDOUT, env=env)
log("locust started (standard: 4 users, 2 minutes)")
time.sleep(30)
if lp.poll() is not None:
    raise SystemExit("locust ended too early, test INVALID")

victim = st[2][0]
log("deleting pod " + victim)
t_del = time.time()
log("kubectl: " + run_out(["kubectl", "delete", "pod", victim, "-n", "app", "--wait=false"]))
restored = None
while time.time() - t_del < 240:
    cur = pods_state()
    if cur:
        log("ready=%d pods=%d %s" % (cur[0], cur[1], cur[2]))
        if cur[0] == 2 and cur[1] == 2 and victim not in cur[2]:
            restored = time.time() - t_del
            break
    time.sleep(3)
log("replica count restored after %s" % ("%.0f s" % restored if restored is not None else "NOT within 240 s"))
log("deployment: " + run_out(["kubectl", "get", "deploy", "kd-parser", "-n", "app"]))

try:
    lp.wait(timeout=240)
except Exception:
    lp.kill()
cf.close()
log("locust finished after %.0f s" % (time.time() - t0))
try:
    with open("results/pod_delete_stats.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Name"] == "Aggregated":
                n, bad = int(row["Request Count"]), int(row["Failure Count"])
                log("Locust Aggregated: %d requests, %d failures = %.3f %%" % (n, bad, 100.0 * bad / max(n, 1)))
except Exception as e:
    log("could not read stats csv: %r" % e)
try:
    log("headers: " + json.dumps(json.load(open("results/pod_delete_headers.json")), indent=1))
except Exception as e:
    log("could not read headers json: %r" % e)
