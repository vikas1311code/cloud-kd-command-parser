import csv
import datetime
import json
import subprocess
import time

HOST = "http://localhost:8081"
LOG = "results/task4_load_balancing_log.txt"
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


def ready_pods():
    out = run_out(["kubectl", "get", "pods", "-n", "app", "-l", "app=kd-parser", "-o", "json"])
    try:
        items = json.loads(out)["items"]
    except Exception:
        return None
    live = [p for p in items if not p["metadata"].get("deletionTimestamp")]
    ready = []
    for p in live:
        conds = {c["type"]: c["status"] for c in p["status"].get("conditions", [])}
        if conds.get("Ready") == "True":
            ready.append(p["metadata"]["name"])
    return len(live), ready


st = ready_pods()
if not st or st[0] != 2 or len(st[1]) != 2:
    raise SystemExit("need exactly 2 pods and both Ready, found %r. Not starting." % (st,))
log("start: exactly 2 Ready replicas: %s" % st[1])
log("hpa: " + run_out(["kubectl", "get", "hpa", "kd-parser", "-n", "app", "--no-headers"]))

t0 = time.time()
with open("results/loadtest_console.txt", "w", encoding="utf-8") as cf:
    subprocess.run(
        ["locust", "-f", "tools/locustfile.py", "--headless", "--users", "4", "--spawn-rate", "4",
         "--run-time", "2m", "--host", HOST, "--csv", "results/loadtest"],
        stdout=cf, stderr=subprocess.STDOUT)
log("locust finished after %.0f s" % (time.time() - t0))
if time.time() - t0 < 100:
    raise SystemExit("Locust ended too early, test INVALID. See results/loadtest_console.txt")

st2 = ready_pods()
log("end: pods %r" % (st2,))
try:
    with open("results/loadtest_stats.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Name"] == "Aggregated":
                n, bad = int(row["Request Count"]), int(row["Failure Count"])
                log("Locust Aggregated: %d requests, %d failures = %.3f %%, median %s ms, 95%% %s ms, %.2f req/s" % (
                    n, bad, 100.0 * bad / max(n, 1), row["50%"], row["95%"], float(row["Requests/s"])))
except Exception as e:
    log("could not read stats csv: %r" % e)

h = json.load(open("results/loadtest_headers.json"))
total = sum(h["per_replica"].values())
log("successful requests by header: total %d" % total)
for name, c in sorted(h["per_replica"].items()):
    log("  %s: %d = %.1f %%" % (name, c, 100.0 * c / total))
shares = [100.0 * c / total for c in h["per_replica"].values()]
log("replicas that answered: %d, smallest share %.1f %% (handout needs each >= 30 %%)" % (len(shares), min(shares)))
log("model versions: %s" % json.dumps(h["per_model_version"]))
