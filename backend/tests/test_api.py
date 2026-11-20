"""End-to-end workflow through the HTTP API (fast model; CASP is covered by tests/casp_*.py)."""
import numpy as np
from fastapi.testclient import TestClient
import app as appmod
from aml import audio_io, generators as G, experiments as E

c = TestClient(appmod.app)


def test_full_workflow():
    wid = c.post("/api/workspace").json()["id"]
    r = c.post(f"/api/workspace/{wid}/demo?kind=hammer&level_dba=58&duration=2.5")
    assert r.status_code == 200 and abs(r.json()["stats"]["LAeq_event"] - 58) < 0.1
    x = G.synth_target("drill", 3.0, 32000, 2, 55.0)
    wav = audio_io.write_wav_bytes(x.astype(np.float32), 32000, "FLOAT")
    r = c.post(f"/api/workspace/{wid}/target", files={"file": ("drill.wav", wav, "audio/wav")}, data={"cal_mode": "pa_float", "distance": "7"})
    assert r.status_code == 200 and abs(r.json()["stats"]["LAeq_event"] - 55) < 0.2
    r = c.post(f"/api/workspace/{wid}/settings", json={"recv_distance": 14.0, "atmosphere": False})
    assert abs(r.json()["stats"]["LAeq_event"] - 49) < 0.3
    c.post(f"/api/workspace/{wid}/settings", json={"recv_distance": 7.0})
    specs = c.get("/api/presets").json()["maskers"][:3]
    r = c.post(f"/api/workspace/{wid}/predict", json={"specs": specs, "p_crit": 0.6})
    items = r.json()["items"]
    assert items[0]["required_masker_LAeq"] is not None and items[0]["map"]["snr_db"]
    r = c.post(f"/api/workspace/{wid}/compare", json={"specs": specs[:2], "p_crit": 0.6, "optimise": False})
    assert len(r.json()["rows"]) == 2
    ex = c.post(f"/api/workspace/{wid}/exp/create", json={"spec": specs[0], "method": "constant", "levels": [-30, -24, -18, -12, -6], "reps": 4}).json()
    sid = ex["id"]; rng = np.random.default_rng(7)
    t = c.post(f"/api/exp/{sid}/next").json()
    assert not t["done"] and "answer" not in t                      # blinded
    assert c.get(f"/api/exp/{sid}/stim/{t['index']}/A.wav").content[:4] == b"RIFF"
    runner = appmod.EXPS[sid]
    while not t["done"]:
        rec = runner.s.trials[t["index"]]
        good = E.simulate_listener(rec["snr_db"], -20.0, 3.0, 0.01, rng)
        resp = rec["answer"] if good else ("A" if rec["answer"] == "B" else "B")
        c.post(f"/api/exp/{sid}/answer", json={"index": t["index"], "response": resp})
        t = c.post(f"/api/exp/{sid}/next").json()
    out = c.post(f"/api/exp/{sid}/model-compare", json={"p_crit": 0.75}).json()
    assert abs(out["human_threshold"] + 20.0) < 4
    for kind in ("csv", "xlsx", "pdf", "config"):
        r = c.get(f"/api/workspace/{wid}/export/{kind}")
        assert r.status_code == 200 and len(r.content) > 200
    assert c.get(f"/api/workspace/{wid}/export/pdf").content[:4] == b"%PDF"


def test_safe_level_cap():
    tgt = G.synth_target("hammer", 1.0, 32000, 1, 60)
    m = G.render_component({"type": "pink", "level": 80}, 12, 32000, 1)
    g, top, capped = E.StimulusFactory(tgt, m, E.StimConfig(cap_dba=70), 1).present_gain(0.0)
    assert capped and top <= 70.001
    assert E.StimulusFactory(tgt, m, E.StimConfig(cap_dba=200), 1).present_gain(0.0)[1] <= E.HARD_CAP_DBA + 1e-6
