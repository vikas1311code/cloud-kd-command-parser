p = "service/app.py"
s = open(p, encoding="utf-8").read()

old_load = s[s.index("def load_model():"):s.index("@asynccontextmanager")]
new_load = '''def load_model():
    for attempt in range(1, 9):
        try:
            download_model()
            tok = AutoTokenizer.from_pretrained(MODEL_DIR)
            tok.pad_token = tok.eos_token
            model = AutoModelForCausalLM.from_pretrained(MODEL_DIR)
            model.eval()
            holder["tok"] = tok
            holder["model"] = model
            state["error"] = None
            state["ready"] = True
            print("model loaded from %s (version %s)" % (MODEL_URI, MODEL_VERSION), flush=True)
            return
        except Exception as e:
            state["error"] = repr(e)
            print("model load failed (attempt %d/8): %s" % (attempt, repr(e)), flush=True)
            time.sleep(min(5 * attempt, 30))
    state["failed"] = True


'''
assert old_load.startswith("def load_model():")
s = s.replace(old_load, new_load)

old_state = 'state = {"ready": False, "error": None}'
assert old_state in s
s = s.replace(old_state, 'state = {"ready": False, "error": None, "failed": False}')

old_imp = "import threading\n"
assert old_imp in s
s = s.replace(old_imp, "import threading\nimport time\n", 1)

old_hz = '''def healthz():
    return {"status": "alive"}'''
assert old_hz in s
s = s.replace(old_hz, '''def healthz():
    if state["failed"]:
        return JSONResponse({"status": "failed", "error": state["error"]}, status_code=503)
    return {"status": "alive"}''')

open(p, "w", encoding="utf-8").write(s)
print("patched")
