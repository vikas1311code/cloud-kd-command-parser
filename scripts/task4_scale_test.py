import datetime
import json
import os
import subprocess
import threading
import time
import urllib.request

HOST = "http://localhost:8081"
OUT = "results/task4_hpa_watch.txt"
CONSOLE = "results/loadtest_scale_console.txt"
HEADERS_OUT = "results/loadtest_scale_headers.json"
MAX_WAIT_AFTER = 480

stop = threading.Event()
seen = {"max_replicas": 0, "first_two": None}


def run(cmd, timeout=25):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return "ERR " + repr(e)


def hpa_replicas():
    row = run(["kubectl", "get", "hpa", "kd-parser", "-n", "app", "--no-headers"])
    try:
        return int(row.split()[-2]), row
    except Exception:
        return None, row


def watcher():
    with open(OUT, "w", encoding="ascii", errors="replace") as f:
        f.write("time  hpa row / pods / top pods\n")
        while not stop.is_set():
            t = datetime.datetime.now().strftime("%H:%M:%S")
            n, row = hpa_replicas()
            if n is not None and n > seen["max_replicas"]:
                seen["max_replicas"] = n
                if n >= 2 and seen["first_two"] is None:
                    seen["first_two"] = t
            pods = run(["kubectl", "get", "pods", "-n", "app", "--no-headers"]).replace("\n", " | ")
            top = run(["kubectl", "top", "pods", "-n", "app", "--no-headers"]).replace("\n", " | ")
            f.write("%s  %s\n    pods: %s\n    top: %s\n" % (t, row, pods, top))
            f.flush()
            stop.wait(5)


ready = run(["kubectl", "get", "deploy", "kd-parser", "-n", "app", "-o", "jsonpath={.status.readyReplicas}"])
if ready != "1":
    raise SystemExit("deployment is not at 1 ready replica (readyReplicas=%r). Not starting." % ready)
n, row = hpa_replicas()
if n != 1:
    raise SystemExit("HPA is at %r replicas, wait until it is 1. Not starting." % n)
body = json.dumps({"text": "set an alarm for seven thirty am tomorrow"}).encode()
req = urllib.request.Request(HOST + "/parse", data=body, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print("sanity request status", r.status)
        if r.status != 200:
            raise SystemExit("sanity request failed")
except Exception as e:
    raise SystemExit("sanity request failed: %r" % e)

th = threading.Thread(target=watcher, daemon=True)
th.start()
print("watcher started, baseline for 15 s")
time.sleep(15)

env = dict(os.environ)
env["LOADTEST_HEADERS_OUT"] = HEADERS_OUT
t_load = time.time()
print("locust running for 3 minutes ...", flush=True)
with open(CONSOLE, "w", encoding="utf-8") as cf:
    subprocess.run(
        ["locust", "-f", "tools/locustfile.py", "--headless",
         "--users", "4", "--spawn-rate", "4", "--run-time", "3m", "--host", HOST,
         "--csv", "results/loadtest_scale"],
        stdout=cf, stderr=subprocess.STDOUT, env=env)
print("locust finished after %.0f s, waiting for scale-down" % (time.time() - t_load), flush=True)
if time.time() - t_load < 150:
    stop.set()
    th.join(timeout=30)
    print("Locust ended after only %.0f s (expected about 180 s). Test INVALID, not measuring scale-down." % (time.time() - t_load))
    print("See results/loadtest_scale_console.txt for the Locust error.")
    raise SystemExit(1)

t_wait = time.time()
back = None
while time.time() - t_wait < MAX_WAIT_AFTER:
    n, row = hpa_replicas()
    print(datetime.datetime.now().strftime("%H:%M:%S"), row, flush=True)
    if n == 1:
        back = time.time() - t_wait
        break
    time.sleep(10)

time.sleep(6)
stop.set()
th.join(timeout=30)
with open("results/task4_hpa_describe.txt", "w", encoding="ascii", errors="replace") as f:
    f.write(run(["kubectl", "describe", "hpa", "kd-parser", "-n", "app"]) + "\n")

print()
print("max replicas seen: %d (first at 2 replicas: %s)" % (seen["max_replicas"], seen["first_two"]))
print("back to 1 replica after load: " + ("%.0f s" % back if back is not None else "NOT within %d s" % MAX_WAIT_AFTER))
print()
with open(CONSOLE, encoding="utf-8", errors="replace") as cf:
    text = cf.read()
i = text.rfind("Successful requests by header")
print(text[i:i + 700] if i >= 0 else "no header summary found")
j = text.rfind("Aggregated")
print(text[j - 200:j + 200] if j >= 0 else "")
