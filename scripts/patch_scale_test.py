p = "scripts/task4_scale_test.py"
s = open(p, encoding="utf-8").read()

old = '[sys.executable, "-m", "locust", "-f", "tools/locustfile.py", "--headless",'
assert old in s
s = s.replace(old, '["locust", "-f", "tools/locustfile.py", "--headless",')

old2 = 'print("locust finished after %.0f s, waiting for scale-down" % (time.time() - t_load), flush=True)'
assert old2 in s
new2 = old2 + '''
if time.time() - t_load < 150:
    stop.set()
    th.join(timeout=30)
    print("Locust ended after only %.0f s (expected about 180 s). Test INVALID, not measuring scale-down." % (time.time() - t_load))
    print("See results/loadtest_scale_console.txt for the Locust error.")
    raise SystemExit(1)'''
s = s.replace(old2, new2)
open(p, "w", encoding="utf-8").write(s)
print("patched")
