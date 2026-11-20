"""Project save/load and the persistent masker-scene library.

A project is a folder ``data/projects/<id>/`` with ``project.json`` (settings, scenes, UI state, last results) and
``arrays.npz`` (raw target samples, background, uploaded masker audio). It can be exported/imported as one ``.amlproj`` zip.

The scene library (``data/library/scenes.json`` + ``data/library/audio/*.npy``) stores every user-made masker scene
automatically so it is available in later projects. Uploaded masker WAVs are kept in the library audio folder.
"""
from __future__ import annotations
import io, json, pathlib, time, uuid, zipfile, re
import numpy as np
from . import audio_io

VERSION = 1


def _slug(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s or "project").strip("_")[:40] or "project"


# ------------------------------------------------------------------ library
class Library:
    def __init__(self, root: pathlib.Path):
        self.root = root
        (root / "audio").mkdir(parents=True, exist_ok=True)
        self.file = root / "scenes.json"

    def scenes(self):
        try:
            return json.loads(self.file.read_text(encoding="utf-8"))
        except Exception:
            return []

    def save_scenes(self, scenes: list[dict]):
        self.file.write_text(json.dumps(scenes, indent=1, ensure_ascii=False), encoding="utf-8")

    def upsert(self, specs: list[dict]):
        cur = {s["name"]: s for s in self.scenes()}
        now = time.time()
        for sp in specs:
            name = sp.get("name")
            if not name:
                continue
            old = cur.get(name)
            cur[name] = {**sp, "_saved": now, "_created": (old or {}).get("_created", now)}
        self.save_scenes(list(cur.values()))
        return len(cur)

    def delete(self, name: str):
        self.save_scenes([s for s in self.scenes() if s.get("name") != name])

    def put_audio(self, cid: str, samples: np.ndarray, label: str):
        np.save(self.root / "audio" / f"{cid}.npy", np.asarray(samples, np.float32))
        (self.root / "audio" / f"{cid}.json").write_text(json.dumps({"label": label}), encoding="utf-8")

    def get_audio(self, cid: str):
        p = self.root / "audio" / f"{cid}.npy"
        if not p.exists():
            return None
        try:
            label = json.loads((self.root / "audio" / f"{cid}.json").read_text(encoding="utf-8")).get("label", cid)
        except Exception:
            label = cid
        return np.load(p).astype(float), label


# ----------------------------------------------------------------- projects
def _clean_scene(s):
    return {k: v for k, v in s.items() if not k.startswith("_")}


def save_project(root: pathlib.Path, pid: str | None, name: str, ws, ui: dict, results: dict, library: Library) -> str:
    pid = pid or f"{_slug(name)}_{uuid.uuid4().hex[:6]}"
    d = root / pid
    d.mkdir(parents=True, exist_ok=True)
    arrays = {}
    if ws.target_raw is not None:
        arrays["target_raw"] = np.asarray(ws.target_raw, np.float32)
    if ws.bg_raw is not None:
        arrays["bg_raw"] = np.asarray(ws.bg_raw, np.float32)
    custom = {}
    for cid, (y, label) in ws.custom_maskers.items():
        arrays[f"custom_{cid}"] = np.asarray(y, np.float32)
        custom[cid] = label
    # custom maskers referenced by library scenes are stored in the library; also keep them inside the project
    np.savez_compressed(d / "arrays.npz", **arrays)
    meta = {
        "version": VERSION, "id": pid, "name": name, "saved": time.time(),
        "workspace": {
            "fs_raw": ws.fs_raw, "raw_meta": ws.raw_meta, "source_label": ws.source_label, "synthetic_target": ws.synthetic_target,
            "cal": ws.cal.to_dict(), "meas_distance": ws.meas_distance, "recv_distance": ws.recv_distance, "atmosphere": ws.atmosphere,
            "temperature_c": ws.temperature_c, "humidity": ws.humidity, "bg_fs": ws.bg_fs,
            "bg_segment": list(ws.bg_segment) if ws.bg_segment else None, "bg_over": ws.bg_over,
            "event": list(ws.event) if ws.event else None, "custom_labels": custom,
        },
        "ui": ui,
        "results": results,
    }
    (d / "project.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    return pid


def load_project(root: pathlib.Path, pid: str, ws):
    """Fill ``ws`` from disk; returns (meta dict)."""
    d = root / pid
    meta = json.loads((d / "project.json").read_text(encoding="utf-8"))
    w = meta["workspace"]
    arr = np.load(d / "arrays.npz") if (d / "arrays.npz").exists() else {}
    ws.name = meta.get("name", pid)
    if "target_raw" in arr:
        ws.target_raw = arr["target_raw"].astype(float)
    ws.fs_raw = w["fs_raw"]; ws.raw_meta = w.get("raw_meta") or {}; ws.source_label = w.get("source_label", "")
    ws.synthetic_target = w.get("synthetic_target", False)
    ws.cal = audio_io.Calibration(**w["cal"])
    for k in ("meas_distance", "recv_distance", "atmosphere", "temperature_c", "humidity", "bg_fs", "bg_over"):
        setattr(ws, k, w[k])
    ws.bg_segment = tuple(w["bg_segment"]) if w.get("bg_segment") else None
    ws.event = tuple(w["event"]) if w.get("event") else None
    if "bg_raw" in arr:
        ws.bg_raw = arr["bg_raw"].astype(float)
    ws.custom_maskers = {cid: (arr[f"custom_{cid}"].astype(float), lab) for cid, lab in (w.get("custom_labels") or {}).items() if f"custom_{cid}" in arr}
    if ws.target_raw is not None:
        ws.prepare()
    return meta


def list_projects(root: pathlib.Path):
    out = []
    for p in sorted(root.glob("*/project.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            out.append({"id": m["id"], "name": m["name"], "saved": m["saved"], "source": m["workspace"].get("source_label", ""),
                        "n_scenes": len(m.get("ui", {}).get("specs", [])), "has_target": m["workspace"].get("fs_raw", 0) > 0})
        except Exception:
            continue
    return out


def delete_project(root: pathlib.Path, pid: str):
    d = root / pid
    if d.exists() and d.is_dir() and (d / "project.json").exists():
        for f in d.iterdir():
            f.unlink()
        d.rmdir()


def export_zip(root: pathlib.Path, pid: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (root / pid).iterdir():
            z.write(f, f.name)
    return buf.getvalue()


def import_zip(root: pathlib.Path, data: bytes) -> str:
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    if "project.json" not in names:
        raise ValueError("not an Acoustic Masking Lab project (project.json missing)")
    meta = json.loads(z.read("project.json").decode("utf-8"))
    pid = f"{_slug(meta.get('name'))}_{uuid.uuid4().hex[:6]}"
    meta["id"] = pid
    d = root / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "project.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    if "arrays.npz" in names:
        (d / "arrays.npz").write_bytes(z.read("arrays.npz"))
    return pid
