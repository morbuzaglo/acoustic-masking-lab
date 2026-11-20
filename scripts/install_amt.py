"""Download and unpack the Auditory Modeling Toolbox 1.6.0 (full package) for the CASP page.

Usage:  python scripts/install_amt.py [target_dir]
Default target: %LOCALAPPDATA%\\AcousticMaskingLab\\amt  (created; the toolbox ends up in <target>/amtoolbox-1.6.0).

The archive is verified against a SHA-256 recorded when this project was built. A mismatch (SourceForge re-packed the file)
only prints a warning, because the content may still be fine; check the version in models/paulick2024.m.
AMT is distributed by its authors under the GPL v3 or later (see THIRD_PARTY_NOTICES.md); it is not copied into this repository.
"""
import hashlib, os, pathlib, sys, urllib.request, zipfile

URL = "https://sourceforge.net/projects/amtoolbox/files/AMT%201.x/amtoolbox-full-1.6.0.zip/download"
SHA256 = "7d350b442f98f4f6fa6349fd38f8e53123f77039d89565caedfae21ce26a3135"
SIZE = 14340832


def main():
    default = pathlib.Path(os.environ.get("LOCALAPPDATA", str(pathlib.Path.home()))) / "AcousticMaskingLab" / "amt"
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else default
    marker = target / "amtoolbox-1.6.0" / "models" / "paulick2024.m"
    if marker.exists():
        print("AMT 1.6.0 already installed:", marker.parent.parent)
        return 0
    target.mkdir(parents=True, exist_ok=True)
    zpath = target / "amtoolbox-full-1.6.0.zip"
    print("Downloading AMT 1.6.0 (about 14 MB) ...")
    req = urllib.request.Request(URL, headers={"User-Agent": "acoustic-masking-lab-installer"})
    with urllib.request.urlopen(req, timeout=300) as r, open(zpath, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    if not zipfile.is_zipfile(zpath):
        print("Download is not a zip file (SourceForge page returned?). Download manually from "
              "https://sourceforge.net/projects/amtoolbox/files/AMT%201.x/ and unzip into", target)
        zpath.unlink(missing_ok=True)
        return 1
    h = hashlib.sha256(zpath.read_bytes()).hexdigest()
    if h != SHA256:
        print(f"WARNING: SHA-256 differs from the recorded value ({h}); size {zpath.stat().st_size} vs {SIZE}.")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(target)
    zpath.unlink(missing_ok=True)
    ok = marker.exists()
    print("Installed:" if ok else "Extraction finished but paulick2024.m not found in", target)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
