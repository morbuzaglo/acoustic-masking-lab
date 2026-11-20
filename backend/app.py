"""FastAPI application: thin HTTP wrapper around aml.* (serves the built frontend from ../frontend/dist)."""
from __future__ import annotations
import json, pathlib, sys, threading, time, uuid
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aml import (service as S, audio_io, generators as G, fastmodel as F, units as U, spectra, experiments as E,
                 casp_bridge as CB, reports as R, optimize as O, projects as P)

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = pathlib.Path(__import__("os").environ.get("AML_DATA_DIR", ROOT / "data"))
(DATA / "sessions").mkdir(parents=True, exist_ok=True)
PROJ = DATA / "projects"; PROJ.mkdir(parents=True, exist_ok=True)
LIB = P.Library(DATA / "library")
S.LIBRARY = LIB
app = FastAPI(title="Acoustic Masking Lab", version="1.0.0")

WS: dict[str, S.Workspace] = {}
RESULTS: dict[str, dict] = {}
EXPS: dict[str, E.Runner] = {}
CASP: dict[str, CB.CaspRun] = {}
LOCK = threading.Lock()


def ws_or_404(wid) -> S.Workspace:
    if wid not in WS:
        raise HTTPException(404, "unknown workspace")
    return WS[wid]


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    return o


def J(o):
    return JSONResponse(clean(o))


@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version, "casp": CB.status(), "fs": S.FS}


@app.get("/api/presets")
def presets():
    defaults = S.default_specs()
    names = {d["name"] for d in defaults}
    lib = {s["name"]: {k: v for k, v in s.items() if not k.startswith("_")} for s in LIB.scenes() if s.get("name")}
    merged = [lib.get(d["name"], d) for d in defaults] + [v for n, v in lib.items() if n not in names]   # edited defaults override the factory version
    return {"maskers": merged, "default_specs": defaults, "default_names": sorted(names), "masker_types": G.TYPES, "target_kinds": G.TARGET_KINDS,
            "defaults": G.DEFAULT_PARAMS, "third_octaves": U.third_octave_centres(100, 10000).tolist()}


# ---------------------------------------------------------- scene library
class LibReq(BaseModel):
    specs: list[dict]


@app.get("/api/library")
def library_get():
    return J({"scenes": [{k: v for k, v in s.items() if not k.startswith("_")} for s in LIB.scenes()]})


@app.put("/api/library")
def library_put(r: LibReq):
    """Upsert user scenes by name (the UI calls this automatically after every change)."""
    n = LIB.upsert(r.specs)
    return {"ok": True, "n": n}


@app.delete("/api/library/{name}")
def library_delete(name: str):
    LIB.delete(name)
    return {"ok": True}


# --------------------------------------------------------------- projects
class SaveReq(BaseModel):
    name: str
    project_id: str | None = None
    ui: dict = {}


@app.get("/api/projects")
def projects_list():
    return P.list_projects(PROJ)


@app.post("/api/workspace/{wid}/project/save")
def project_save(wid: str, r: SaveReq):
    ws = ws_or_404(wid)
    defaults = {d["name"]: d for d in S.default_specs()}
    LIB.upsert([s for s in r.ui.get("specs", []) if defaults.get(s.get("name")) != s])
    res = clean({k: v for k, v in RESULTS.get(wid, {}).items() if k in ("predict", "compare", "casp", "shape", "experiments")})
    pid = P.save_project(PROJ, r.project_id, r.name, ws, r.ui, res, LIB)
    return {"project_id": pid}


@app.post("/api/project/{pid}/load")
def project_load(pid: str):
    if not (PROJ / pid / "project.json").exists():
        raise HTTPException(404, "unknown project")
    wid = uuid.uuid4().hex[:10]
    ws = S.Workspace(id=wid)
    try:
        meta = P.load_project(PROJ, pid, ws)
    except Exception as e:
        raise HTTPException(400, f"cannot load project: {e}")
    WS[wid] = ws
    RESULTS[wid] = meta.get("results", {})
    return J({"wid": wid, "name": meta["name"], "project_id": pid, "ui": meta.get("ui", {}), "results": meta.get("results", {}),
              "target": ws.target_summary() if ws.target_event is not None else None})


@app.delete("/api/project/{pid}")
def project_delete(pid: str):
    P.delete_project(PROJ, pid)
    return {"ok": True}


@app.get("/api/project/{pid}/download")
def project_download(pid: str):
    if not (PROJ / pid / "project.json").exists():
        raise HTTPException(404)
    return Response(P.export_zip(PROJ, pid), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={pid}.amlproj"})


@app.post("/api/project/import")
async def project_import(file: UploadFile = File(...)):
    try:
        pid = P.import_zip(PROJ, await file.read())
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"project_id": pid}


# ------------------------------------------------------------------ workspace
@app.post("/api/workspace")
def new_workspace():
    wid = uuid.uuid4().hex[:10]
    WS[wid] = S.Workspace(id=wid)
    RESULTS[wid] = {}
    return {"id": wid}


@app.post("/api/workspace/{wid}/demo")
def demo_target(wid: str, kind: str = "hammer", level_dba: float = 60.0, duration: float = 4.0, seed: int = 1):
    ws = ws_or_404(wid)
    if kind not in G.TARGET_KINDS:
        raise HTTPException(400, "unknown kind")
    ws.target_raw = G.synth_target(kind, duration, S.FS, seed, level_dba)
    ws.fs_raw = S.FS
    ws.cal = audio_io.Calibration("pa_float")
    ws.synthetic_target = True
    ws.source_label = f"SYNTHETIC {G.TARGET_KINDS[kind]}, {level_dba:g} dBA at {ws.meas_distance:g} m"
    ws.event = None
    ws.prepare()
    return J(ws.target_summary())


@app.post("/api/workspace/{wid}/target")
async def upload_target(wid: str, file: UploadFile = File(...), cal_mode: str = Form("pa_float"), cal_value: float = Form(1.0),
                        cal_t0: float = Form(0.0), cal_t1: float | None = Form(None), cal_weighting: str = Form("Z"),
                        distance: float = Form(7.0)):
    ws = ws_or_404(wid)
    try:
        x, fs, meta = audio_io.read_wav_bytes(await file.read())
    except Exception as e:
        raise HTTPException(400, f"cannot read WAV: {e}")
    ws.target_raw, ws.fs_raw, ws.raw_meta = x, fs, meta
    ws.cal = audio_io.Calibration(cal_mode, cal_value, cal_t0, cal_t1, cal_weighting)
    ws.meas_distance = ws.recv_distance = distance
    ws.synthetic_target = False
    ws.source_label = file.filename or "upload"
    ws.event = None
    try:
        ws.prepare()
    except Exception as e:
        raise HTTPException(400, str(e))
    return J(ws.target_summary())


class TargetSettings(BaseModel):
    cal_mode: str | None = None
    cal_value: float | None = None
    cal_t0: float | None = None
    cal_t1: float | None = None
    cal_weighting: str | None = None
    meas_distance: float | None = None
    recv_distance: float | None = None
    atmosphere: bool | None = None
    temperature_c: float | None = None
    humidity: float | None = None
    event: list[float] | None = None
    bg_segment: list[float] | None = None
    bg_clear: bool = False
    bg_over: float | None = None


@app.post("/api/workspace/{wid}/settings")
def target_settings(wid: str, s: TargetSettings):
    ws = ws_or_404(wid)
    if ws.target_raw is None:
        raise HTTPException(400, "no target")
    c = ws.cal
    for k in ("mode", "value", "t0", "t1", "weighting"):
        v = getattr(s, "cal_" + k)
        if v is not None:
            setattr(c, k, v)
    for k in ("meas_distance", "recv_distance", "atmosphere", "temperature_c", "humidity", "bg_over"):
        v = getattr(s, k)
        if v is not None:
            setattr(ws, k, v)
    if s.event:
        ws.event = (s.event[0], s.event[1])
    if s.bg_clear:
        ws.bg_segment = None; ws.bg_raw = None
    if s.bg_segment:
        ws.bg_segment = (s.bg_segment[0], s.bg_segment[1])
    try:
        ws.prepare()
    except Exception as e:
        raise HTTPException(400, str(e))
    return J(ws.target_summary())


@app.post("/api/workspace/{wid}/background")
async def upload_background(wid: str, file: UploadFile = File(...)):
    ws = ws_or_404(wid)
    x, fs, _ = audio_io.read_wav_bytes(await file.read())
    ws.bg_raw, ws.bg_fs, ws.bg_segment = x, fs, None
    ws.prepare()
    return J(ws.target_summary())


@app.post("/api/workspace/{wid}/masker-upload")
async def upload_masker(wid: str, file: UploadFile = File(...), cal_mode: str = Form("relative")):
    ws = ws_or_404(wid)
    x, fs, meta = audio_io.read_wav_bytes(await file.read())
    y = audio_io.resample(x, fs, S.FS)
    if cal_mode == "pa_float":
        pass
    cid = uuid.uuid4().hex[:8]
    ws.custom_maskers[cid] = (y, file.filename)
    LIB.put_audio(cid, y, file.filename or cid)      # kept so scenes using it stay usable in later projects
    sp = spectra.spectra_payload(y * (1 if cal_mode == "pa_float" else 1), S.FS)
    return {"custom_id": cid, "name": file.filename, "duration_s": len(y) / S.FS, "relative": cal_mode != "pa_float",
            "spectra": clean(sp)}


class MaskerPreviewReq(BaseModel):
    spec: dict
    duration: float = 6.0
    seed: int = 1


@app.post("/api/workspace/{wid}/masker-preview")
def masker_preview(wid: str, r: MaskerPreviewReq):
    ws = ws_or_404(wid)
    try:
        m = ws.render_masker(r.spec, r.duration, r.seed)
    except Exception as e:
        raise HTTPException(400, str(e))
    t, lo, hi = spectra.waveform_envelope(m, S.FS, 1200)
    tt, ff, Ls = spectra.spectrogram_db(m, S.FS, 0.032, 0.02, 12000, 400)
    sp = spectra.spectra_payload(m, S.FS)
    return J({"waveform": {"t": t, "lo": lo, "hi": hi}, "spectra": sp,
              "spectrogram": {"t": np.round(tt, 3), "f": np.round(ff, 1), "L": np.round(Ls, 1)},
              "metrics": S.masker_metrics(m)})


@app.get("/api/workspace/{wid}/audio/{what}.wav")
def audio_get(wid: str, what: str, masker: str | None = None, snr: float | None = None, seed: int = 1, kind: str = "pa"):
    """what = target | mix. mix needs masker=<json spec>; level in the spec is the physical receiver level."""
    ws = ws_or_404(wid)
    if what == "target":
        return Response(R.audio_io.write_wav_bytes(ws.target_event.astype(np.float32), S.FS, "FLOAT"), media_type="audio/wav")
    spec = json.loads(masker or "{}")
    dur = len(ws.target_event) / S.FS
    m = ws.render_masker(spec, max(dur, 1.0), seed)
    tg = ws.target_event
    if snr is not None:  # re-level target so that LAeq,target - LAeq,masker = snr
        tg = tg * 10 ** ((U.laeq(m, S.FS) + snr - U.laeq(tg, S.FS)) / 20)
    return Response(R.mix_wav(tg, m, S.FS, as_pascal=(kind == "pa")), media_type="audio/wav")


@app.get("/api/workspace/{wid}/listen.wav")
def listen_wav(wid: str, masker: str, snr: float | None = None, target: int = 1, seed: int = 1, spl_fs: float = 100.0,
               cap: float = 70.0, offset: float = 0.0):
    """Headphone-safe preview: masker (+ target at ``snr`` dB re masker LAeq) through the headphone calibration,
    with the presented LAeq capped (hard cap 85 dBA) by scaling target and masker together."""
    ws = ws_or_404(wid)
    spec = json.loads(masker)
    dur = max(len(ws.target_event) / S.FS + 0.7, 2.0)
    m = ws.render_masker(spec, dur, seed)
    cfg = E.StimConfig(level_offset_db=offset, cap_dba=min(cap, E.HARD_CAP_DBA), spl_at_full_scale_db=spl_fs)
    mlaeq = U.laeq(m, S.FS)
    sig = m.copy()
    L = mlaeq
    if target and snr is not None:
        tg = ws.target_event * 10 ** ((mlaeq + snr - U.laeq(ws.target_event, S.FS)) / 20)
        i0 = int(0.35 * S.FS)
        sig[i0:i0 + len(tg)] += tg[: len(sig) - i0]
        L = max(mlaeq, mlaeq + snr)
    elif target:
        tg = ws.target_event
        i0 = int(0.35 * S.FS)
        sig[i0:i0 + len(tg)] += tg[: len(sig) - i0]
        L = max(mlaeq, U.laeq(tg, S.FS))
    L += offset
    red = max(0.0, L - cfg.cap_dba)
    fac = E.StimulusFactory.__new__(E.StimulusFactory)
    fac.cfg = cfg
    wav, limited = E.StimulusFactory.to_wav(fac, sig * 10 ** ((offset - red) / 20))
    return Response(wav, media_type="audio/wav", headers={"X-Presented-LAeq": f"{L - red:.1f}", "X-Reduced-dB": f"{red:.1f}",
                                                         "Access-Control-Expose-Headers": "X-Presented-LAeq, X-Reduced-dB", "Cache-Control": "no-store"})


# -------------------------------------------------------------- predictions
class PredictReq(BaseModel):
    specs: list[dict]
    p_crit: float = 0.60
    include_map: bool = True
    optimise: bool = False
    lam: float = 0.5
    offset_db: float = 0.0
    quiet_offset_db: float = 0.0


@app.post("/api/workspace/{wid}/predict")
def predict(wid: str, r: PredictReq):
    ws = ws_or_404(wid)
    prm = F.Params(quiet_offset_db=r.quiet_offset_db)
    out = []
    for i, spec in enumerate(r.specs):
        try:
            out.append(S.predict_masker(ws, spec, r.p_crit, prm, include_map=(r.include_map and i == 0), offset_db=r.offset_db))
        except Exception as e:
            raise HTTPException(400, f"{spec.get('name')}: {e}")
    RESULTS[wid]["predict"] = {"p_crit": r.p_crit, "items": out}
    return J({"items": out, "model": "ERB-EDM (fast)"})


@app.post("/api/workspace/{wid}/compare")
def compare(wid: str, r: PredictReq):
    ws = ws_or_404(wid)
    prm = F.Params(quiet_offset_db=r.quiet_offset_db)
    rows = S.compare_maskers(ws, r.specs, r.p_crit, r.lam, r.optimise, prm, r.offset_db)
    RESULTS[wid]["compare"] = rows
    pred = RESULTS[wid].get("predict", {}).get("items")
    return J({"rows": rows, "model": "ERB-EDM (fast)"})


class ShapeReq(BaseModel):
    spec: dict
    p_crit: float = 0.60
    lam: float = 0.5
    la_cap: float | None = None


@app.post("/api/workspace/{wid}/optimise-shape")
def optimise_shape(wid: str, r: ShapeReq):
    ws = ws_or_404(wid)
    dur = max(len(ws.target_event) / S.FS, 1.0)
    m = ws.render_masker(r.spec, dur, S.SEEDS_MC[0])
    sc = O.build_scene(ws.target_event, m, S.FS)
    res = O.optimise_shape(sc, r.p_crit, r.lam, r.la_cap)
    if res.get("ok"):
        g = np.array(res["gains_db"])
        shaped = O.shaping_filter(m, S.FS, sc.centres, g)
        res["metrics_optimised"] = S.masker_metrics(shaped)
        flat_g = res["flat"]["gain_db"]
        res["metrics_flat"] = S.masker_metrics(m * 10 ** (flat_g / 20))
        res["target_spectrum"] = clean(spectra.spectra_payload(ws.target_event, S.FS)["third_octave"])
        res["masker_spectrum_opt"] = clean(spectra.spectra_payload(shaped, S.FS)["third_octave"])
        res["masker_spectrum_flat"] = clean(spectra.spectra_payload(m * 10 ** (flat_g / 20), S.FS)["third_octave"])
        RESULTS[wid]["shape"] = res
    return J(res)


# --------------------------------------------------------------------- CASP
class CaspReq(BaseModel):
    specs: list[dict]
    gm_db: list[float]                     # masker level offsets relative to the spec levels
    realisations: int = 4
    max_duration: float = 1.0
    model: str = "paulick2024"
    t_start: float | None = None
    p_crit: float = 0.75


@app.get("/api/casp/status")
def casp_status():
    return CB.status()


@app.post("/api/workspace/{wid}/casp/start")
def casp_start(wid: str, r: CaspReq):
    ws = ws_or_404(wid)
    if not CB.available():
        raise HTTPException(503, "MATLAB / AMT not available on this machine")
    tgt = ws.target_event
    n_max = int(r.max_duration * S.FS)
    if len(tgt) > n_max:   # most energetic window of max_duration
        hop = S.FS // 20
        e = np.convolve(tgt ** 2, np.ones(n_max), mode="valid")[::hop]
        i = int(np.argmax(e)) * hop if r.t_start is None else int(r.t_start * S.FS)
        tgt = tgt[i:i + n_max]
    dur = len(tgt) / S.FS
    maskers = []
    for spec in r.specs:
        maskers.append([ws.render_masker(spec, dur, 100 + k) for k in range(max(3, r.realisations))])
    job = CB.CaspRun()
    cid = uuid.uuid4().hex[:8]
    job.start(tgt, maskers, S.FS, r.gm_db, [s.get("name", f"m{i}") for i, s in enumerate(r.specs)], model=r.model)
    CASP[cid] = job
    job.meta = {"specs": [s.get("name") for s in r.specs], "gm_db": r.gm_db, "p_crit": r.p_crit,
                "ref_laeq": [float(U.laeq(m[0], S.FS)) for m in maskers], "tgt_laeq": float(U.laeq(tgt, S.FS)), "wid": wid}
    return {"job": cid}


@app.get("/api/casp/{cid}")
def casp_get(cid: str):
    j = CASP.get(cid)
    if not j:
        raise HTTPException(404, "unknown job")
    info = j.info()
    if j.state == "done":
        res = j.result
        meta = j.meta
        Pc = CB.p_table(res)
        Pr = CB.p_table(res, CB.INVAR_AMT)
        gm = meta["gm_db"]
        items = []
        for i, name in enumerate(meta["specs"]):
            thr = CB.interpolate_threshold(gm, Pc[i], meta["p_crit"])
            items.append({"name": name, "P_cal": Pc[i].tolist(), "P_raw": Pr[i].tolist(),
                          "threshold_gm_db": thr, "threshold_LAeq": (meta["ref_laeq"][i] + thr) if np.isfinite(thr) else None})
        info["result"] = {"items": items, "gm_db": gm, "levels_LAeq": [[l + g for g in gm] for l in meta["ref_laeq"]],
                          "tgt_LAeq": meta["tgt_laeq"], "in_var_calibrated": CB.invar_calibrated(), "in_var_amt": CB.INVAR_AMT,
                          "rep_map": res.get("rep_map"), "elapsed_s": res.get("elapsed_s"), "model": res.get("model"),
                          "n_realisations": res.get("n_realisations")}
        RESULTS.setdefault(meta["wid"], {})["casp"] = info["result"]
    return J(info)


@app.delete("/api/casp/{cid}")
def casp_cancel(cid: str):
    if cid in CASP:
        CASP[cid].cancel()
    return {"ok": True}


@app.get("/api/validation")
def validation():
    d = ROOT / "docs" / "validation"
    out = {}
    for n in ("casp_validation", "casp_calibration", "model_validation"):
        p = d / f"{n}.json"
        if p.exists():
            out[n] = json.loads(p.read_text())
    return J(out)


# -------------------------------------------------------------- experiments
class ExpReq(BaseModel):
    participant: str = "P01"
    spec: dict
    method: str = "staircase"              # staircase | constant
    rule: str = "2down1up"
    n_tracks: int = 2
    n_reversals: int = 10
    start_snr: float = 6.0
    levels: list[float] = [-24, -18, -12, -6, 0]
    reps: int = 10
    spl_at_full_scale_db: float = 100.0
    calibrated: bool = False
    cap_dba: float = 75.0
    level_offset_db: float = 0.0
    seed: int = 1
    p_crit: float = 0.75


@app.post("/api/workspace/{wid}/exp/create")
def exp_create(wid: str, r: ExpReq):
    ws = ws_or_404(wid)
    cfg = E.StimConfig(level_offset_db=r.level_offset_db, cap_dba=min(r.cap_dba, E.HARD_CAP_DBA),
                       spl_at_full_scale_db=r.spl_at_full_scale_db, calibrated=r.calibrated)
    tdur = len(ws.target_event) / S.FS
    need = 2 * (max(cfg.interval_s, tdur + 2 * cfg.lead_s)) + 2
    m = ws.render_masker(r.spec, max(need, 12.0), r.seed)
    fac = E.StimulusFactory(ws.target_event, m, cfg, r.seed)
    sid = uuid.uuid4().hex[:10]
    sess = E.Session(id=sid, participant=r.participant, created=time.time(), method=r.method,
                     config={**r.model_dump(exclude={"spec"}), "spec": r.spec, "wid": wid, "target": ws.source_label},
                     levels=r.levels, reps=r.reps)
    EXPS[sid] = E.Runner(sess, fac)
    sess.config["starts"] = [r.start_snr, r.start_snr - 4]
    EXPS[sid] = E.Runner(sess, fac)
    return {"id": sid, "masker_LAeq": fac.masker_laeq, "target_LAeq": fac.target_laeq, "uncalibrated_warning": not r.calibrated}


@app.post("/api/exp/{sid}/next")
def exp_next(sid: str):
    r = EXPS.get(sid)
    if not r:
        raise HTTPException(404)
    t = r.next_trial()
    if t is None:
        E.save_session(r.s, DATA / "sessions")
        return J({"done": True, "summary": r.summary(r.s.config.get("p_crit"))})
    return J({"done": False, **t})


@app.get("/api/exp/{sid}/stim/{idx}/{which}.wav")
def exp_stim(sid: str, idx: int, which: str):
    r = EXPS.get(sid)
    if not r or idx not in r.pending:
        raise HTTPException(404)
    return Response(r.stim(idx, which), media_type="audio/wav", headers={"Cache-Control": "no-store"})


class AnswerReq(BaseModel):
    index: int
    response: str


@app.post("/api/exp/{sid}/answer")
def exp_answer(sid: str, a: AnswerReq):
    r = EXPS.get(sid)
    if not r:
        raise HTTPException(404)
    ok = r.answer(a.index, a.response)
    prog = {"n": len(r.s.trials), "done": r.s.done}
    if r.s.method == "staircase":
        prog["reversals"] = [len(st.reversals) for st in r.stairs]
        prog["current"] = [st.value for st in r.stairs]
    if r.s.done:
        E.save_session(r.s, DATA / "sessions")
    return J({"correct": ok, "progress": prog})   # feedback is optional in the UI


@app.get("/api/exp/{sid}/summary")
def exp_summary(sid: str):
    r = EXPS.get(sid)
    if not r:
        raise HTTPException(404)
    s = r.summary(r.s.config.get("p_crit"))
    s["trials"] = [{k: t[k] for k in ("index", "track", "snr_db", "correct", "rt_s", "capped")} for t in r.s.trials if t["correct"] is not None]
    s["tracks"] = r.s.tracks
    s["config"] = {k: v for k, v in r.s.config.items() if k != "spec"}
    return J(s)


class CompareReq(BaseModel):
    p_crit: float = 0.75
    quiet_offset_db: float = 0.0


@app.post("/api/exp/{sid}/model-compare")
def exp_model_compare(sid: str, c: CompareReq):
    """Human psychometric function vs the fast-model prediction for the same target and masker, and the
    participant-specific offset (human threshold - model threshold)."""
    r = EXPS.get(sid)
    if not r:
        raise HTTPException(404)
    ws = ws_or_404(r.s.config["wid"])
    summ = r.summary(c.p_crit)
    pm = summ["psychometric"]
    if not pm.get("ok"):
        raise HTTPException(400, "not enough data for a psychometric fit yet")
    dur = max(len(ws.target_event) / S.FS, 1.0)
    thr_list, curves = [], []
    grid = np.linspace(min(pm["levels"]) - 10, max(pm["levels"]) + 10, 60)
    for seed in S.SEEDS_MC:
        m = ws.render_masker(r.s.config["spec"], dur, seed)
        an = S._analysis_for(ws, m, F.Params(quiet_offset_db=c.quiet_offset_db))
        base = U.laeq(ws.target_event, S.FS) - U.laeq(m, S.FS)
        g = an.solve(c.p_crit, "target")
        thr_list.append(base + g)
        curves.append([an.p2afc(x - base, 0.0) for x in grid])
    thr_model = float(np.nanmean(thr_list))
    off = pm["threshold"] - thr_model
    out = {"human_threshold": pm["threshold"], "human_ci95": pm["ci95"], "model_threshold": thr_model,
           "model_sd_mc": float(np.nanstd(thr_list)), "offset_db": float(off),
           "offset_ci95": [pm["ci95"][0] - thr_model, pm["ci95"][1] - thr_model],
           "model_curve": {"x": grid.tolist(), "p": np.mean(curves, axis=0).tolist()}, "psychometric": pm,
           "p_crit": c.p_crit, "interpretation": "positive offset = the participant needs a higher SNR than the model predicts"}
    RESULTS.setdefault(ws.id, {}).setdefault("experiments", {})[sid] = out
    return J(out)


@app.get("/api/sessions")
def sessions():
    rows = []
    for p in sorted((DATA / "sessions").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        rows.append({"id": d["id"], "participant": d["participant"], "created": d["created"], "method": d["method"],
                     "n_trials": len(d["trials"])})
    return rows


# ------------------------------------------------------------------ export
@app.get("/api/workspace/{wid}/export/{kind}")
def export(wid: str, kind: str):
    ws = ws_or_404(wid)
    res = RESULTS.get(wid, {})
    cmp_rows = res.get("compare", [])
    pred = res.get("predict", {}).get("items", [])
    meta = {"target": ws.source_label, "synthetic_target": ws.synthetic_target, "measurement_distance_m": ws.meas_distance,
            "receiver_distance_m": ws.recv_distance, "calibration": ws.cal.to_dict(), "event_window_s": ws.event,
            "target_LAeq_event_dB": U.laeq(ws.target_event, S.FS), "criterion_P2AFC": res.get("predict", {}).get("p_crit", 0.6),
            "fast_model": "ERB-EDM v1 (eta=%.4f)" % F.default_eta(fs=S.FS), "casp": "AMT 1.6.0 paulick2024 (only if run)",
            "sampling_rate_analysis_Hz": S.FS}
    trials, psy, mvh = [], [], []
    for sid, ex in (res.get("experiments") or {}).items():
        r = EXPS.get(sid)
        if r:
            trials += [{"session": sid, "participant": r.s.participant, **{k: t[k] for k in ("index", "track", "snr_db", "answer", "response", "correct", "rt_s")}} for t in r.s.trials if t["correct"] is not None]
        pm = ex["psychometric"]
        psy.append({"session": sid, "mu": pm["mu"], "sigma": pm["sigma"], "threshold": pm["threshold"], "ci_lo": pm["ci95"][0], "ci_hi": pm["ci95"][1], "p_crit": pm["p_crit"]})
        mvh.append({"session": sid, "human_threshold_dB": ex["human_threshold"], "model_threshold_dB": ex["model_threshold"], "offset_dB": ex["offset_db"]})
    payload = {"meta": meta, "compare": cmp_rows, "curves": [{"name": p["name"], **p["curve_masker"]} for p in pred],
               "trials": trials, "psychometric": psy, "model_vs_human": mvh,
               "spectra": spectra.spectra_payload(ws.target_event, S.FS)}
    if res.get("experiments"):
        sid, ex = list(res["experiments"].items())[-1]
        pm = ex["psychometric"]
        payload["psychometric_curve"] = {"x": pm["curve"]["x"], "p": pm["curve"]["p"], "levels": pm["levels"], "k": pm["k"], "n": pm["n"], "model": ex["model_curve"]}
        payload["experiment_text"] = {"Human threshold": f'{ex["human_threshold"]:.1f} dB SNR (95 % CI {ex["human_ci95"][0]:.1f} to {ex["human_ci95"][1]:.1f})',
                                      "Model threshold": f'{ex["model_threshold"]:.1f} dB SNR', "Participant offset": f'{ex["offset_db"]:+.1f} dB'}
    if kind == "csv":
        return Response(R.to_csv(R.compare_rows_flat(cmp_rows)), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=masking_results.csv"})
    if kind == "xlsx":
        return Response(R.to_xlsx(payload), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=masking_results.xlsx"})
    if kind == "pdf":
        return Response(R.to_pdf(payload), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=masking_report.pdf"})
    if kind == "config":
        cfg = {"version": 1, "meta": meta, "maskers": [p["name"] for p in pred], "results_keys": list(res.keys())}
        return Response(json.dumps(clean(cfg), indent=1), media_type="application/json", headers={"Content-Disposition": "attachment; filename=masking_config.json"})
    raise HTTPException(404)


class ConfigReq(BaseModel):
    config: dict


# ---------------------------------------------------------------- frontend
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
