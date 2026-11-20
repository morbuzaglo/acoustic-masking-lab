"""Manual probe: run /predict against a running server and print the shape of the response."""
import json, time, urllib.request
B = "http://127.0.0.1:8770"
post = lambda u, d=None: json.load(urllib.request.urlopen(urllib.request.Request(B + u, data=json.dumps(d).encode() if d is not None else b"", headers={"Content-Type": "application/json"}), timeout=600))
w = post("/api/workspace")["id"]
post(f"/api/workspace/{w}/demo?kind=hammer&level_dba=60&duration=3")
specs = json.load(urllib.request.urlopen(B + "/api/presets"))["maskers"][:1]
t = time.time()
r = post(f"/api/workspace/{w}/predict", {"specs": specs, "p_crit": 0.6, "include_map": True})
print("seconds", round(time.time() - t, 1))
it = r["items"][0]
print({k: (type(v).__name__, len(v) if hasattr(v, "__len__") else v) for k, v in it.items()})
m = it["map"]
flat = [x for row in m["snr_db"] for x in row]
print(len(m["fc"]), len(m["t"]), len(m["snr_db"]), len(m["snr_db"][0]), min(flat), max(flat), sum(x is None for x in flat))
print(it["required_masker_LAeq"], it["uncertainty"])
