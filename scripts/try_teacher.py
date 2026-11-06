import json, sys, time, urllib.request

prompt = open("prompts/teacher_prompt.txt", encoding="utf-8").read()
n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
cmds = [json.loads(l) for l in open("data/commands_pool.jsonl", encoding="utf-8")][:n]

for c in cmds:
    body = {
        "model": "phi3.5",
        "prompt": prompt.replace("{command}", c["text"]),
        "stream": False,
        "options": {"temperature": 0, "seed": 42, "num_predict": 120},
    }
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t = time.time()
    out = json.loads(urllib.request.urlopen(req, timeout=600).read())
    print(c["id"], "|", c["text"])
    print("   ->", repr(out["response"]))
    print("   %.1f s" % (time.time() - t))
