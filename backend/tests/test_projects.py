"""Project save/load round trip, project file import/export, and the automatic scene library."""
import io, zipfile
import numpy as np
from fastapi.testclient import TestClient
import app as appmod
from aml import audio_io, generators as G

c = TestClient(appmod.app)


def _ws_with_target():
    wid = c.post("/api/workspace").json()["id"]
    x = G.synth_target("drill", 2.5, 32000, 3, 57.0)
    wav = audio_io.write_wav_bytes(x.astype(np.float32), 32000, "FLOAT")
    r = c.post(f"/api/workspace/{wid}/target", files={"file": ("drill.wav", wav, "audio/wav")}, data={"cal_mode": "pa_float", "distance": "7"})
    assert r.status_code == 200
    return wid, r.json()


def test_project_round_trip_restores_everything():
    wid, t0 = _ws_with_target()
    c.post(f"/api/workspace/{wid}/settings", json={"recv_distance": 14.0, "atmosphere": False, "event": [0.2, 2.0]})
    t1 = c.post(f"/api/workspace/{wid}/settings", json={"temperature_c": 12.0}).json()
    ui = {"specs": [{"name": "My scene", "components": [{"type": "pink", "level": 41, "weighting": "A"}]}], "selected": [0], "pCrit": 0.7, "offsetDb": -2.5,
          "safety": {"spl_fs": 104, "cap": 66, "calibrated": True}}
    pid = c.post(f"/api/workspace/{wid}/project/save", json={"name": "Round trip", "ui": ui}).json()["project_id"]
    assert any(p["id"] == pid for p in c.get("/api/projects").json())
    r = c.post(f"/api/project/{pid}/load").json()
    assert r["wid"] != wid and r["ui"] == ui
    assert abs(r["target"]["stats"]["LAeq_event"] - t1["stats"]["LAeq_event"]) < 1e-6      # same calibrated target and window
    assert r["target"]["distance"]["receiver"] == 14.0 and r["target"]["event"] == [0.2, 2.0]
    # the restored workspace works: predict on it
    p = c.post(f"/api/workspace/{r['wid']}/predict", json={"specs": ui["specs"], "p_crit": 0.7, "include_map": False})
    assert p.status_code == 200 and p.json()["items"][0]["name"] == "My scene"


def test_project_file_export_and_import():
    wid, _ = _ws_with_target()
    pid = c.post(f"/api/workspace/{wid}/project/save", json={"name": "Portable", "ui": {"specs": []}}).json()["project_id"]
    blob = c.get(f"/api/project/{pid}/download").content
    assert "project.json" in zipfile.ZipFile(io.BytesIO(blob)).namelist()
    new = c.post("/api/project/import", files={"file": ("p.amlproj", blob, "application/zip")}).json()["project_id"]
    assert new != pid and c.post(f"/api/project/{new}/load").status_code == 200
    assert c.post("/api/project/import", files={"file": ("bad.amlproj", b"not a zip", "application/zip")}).status_code == 400
    c.delete(f"/api/project/{new}")
    assert not any(p["id"] == new for p in c.get("/api/projects").json())


def test_scene_library_persists_and_feeds_presets():
    spec = {"name": "Library test scene", "components": [{"type": "water", "level": 38, "weighting": "A"}], "shape": {"centres": [100, 1000, 10000], "gains_db": [0, 5, 0]}}
    assert c.put("/api/library", json={"specs": [spec]}).json()["ok"]
    presets = c.get("/api/presets").json()
    assert any(m["name"] == "Library test scene" and m["shape"] for m in presets["maskers"])   # available to every later project
    # editing a factory scene is also kept (overrides the default) and the default list stays available
    edited = {**presets["default_specs"][0], "components": [{"type": "pink", "level": 55, "weighting": "A"}]}
    c.put("/api/library", json={"specs": [edited]})
    again = c.get("/api/presets").json()
    assert again["maskers"][0]["components"][0]["level"] == 55 and again["default_specs"][0]["components"][0]["level"] == 40
    c.delete("/api/library/Library test scene"); c.delete(f"/api/library/{edited['name']}")
    assert not any(m["name"] == "Library test scene" for m in c.get("/api/presets").json()["maskers"])


def test_uploaded_masker_audio_is_reusable_from_library():
    wid, _ = _ws_with_target()
    y = G.render_component({"type": "pink", "level": 40}, 3.0, 32000, 9)
    wav = audio_io.write_wav_bytes(y.astype(np.float32), 32000, "FLOAT")
    up = c.post(f"/api/workspace/{wid}/masker-upload", files={"file": ("bg.wav", wav, "audio/wav")}).json()
    spec = {"name": "Uploaded bg scene", "components": [{"type": "custom", "custom_id": up["custom_id"], "level": 42, "weighting": "A"}]}
    c.put("/api/library", json={"specs": [spec]})
    wid2 = c.post("/api/workspace").json()["id"]          # a brand-new project, nothing uploaded in it
    r = c.post(f"/api/workspace/{wid2}/masker-preview", json={"spec": spec, "duration": 2.0})
    assert r.status_code == 200 and abs(r.json()["spectra"]["LAeq"] - 42) < 0.3
    c.delete("/api/library/Uploaded bg scene")


def test_shape_scene_renders_at_optimised_level():
    from aml import service as S, optimize as O
    ws = S.Workspace(id="t"); ws.target_raw = G.synth_target("hammer", 1.5, 32000, 1, 60); ws.fs_raw = 32000; ws.prepare()
    base = {"name": "b", "components": [{"type": "pink", "level": 40, "weighting": "A"}]}
    m = ws.render_masker(base, 1.5, 11)
    sc = O.build_scene(ws.target_event, m, 32000)
    res = O.optimise_shape(sc, 0.6, 0.0)
    shaped = ws.render_masker({**base, "shape": {"centres": res["centres"], "gains_db": res["gains_db"]}}, 1.5, 11)
    from aml import units as U
    assert abs(U.laeq(shaped, 32000) - res["LAeq"]) < 0.3
