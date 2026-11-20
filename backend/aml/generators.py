"""Deterministic synthesis of masker sounds (wind, crickets, flowing water, rain, leaves, coloured noise).

All generators return a *unit-RMS* signal; ``render_component`` applies spectral shaping, temporal
variation and finally sets the physical level at the receiver (Pa). Every random process is drawn
from a ``numpy.random.Generator`` seeded from (seed, component index) so a configuration reproduces
bit-exactly.

These are signal-level *models of the acoustic character* of the sounds (spectral shape, temporal
modulation, event statistics); they are not physical simulations of the sources. Spectral envelopes
follow commonly reported shapes (e.g. pink 1/f, rain drop-impact bands) but were tuned by ear/analysis
in this project and are labelled SYNTHETIC in every export.
"""
from __future__ import annotations
import numpy as np
from scipy import signal
from . import units as U

FS_DEFAULT = 32000

TYPES = {
    "white": "White noise",
    "pink": "Pink noise (1/f)",
    "brown": "Brown noise (1/f²)",
    "wind": "Wind with gusts",
    "crickets": "Crickets chorus",
    "water": "Flowing water (stream)",
    "rain": "Rain",
    "leaves": "Rustling leaves",
}

DEFAULT_PARAMS = {
    "white": {},
    "pink": {},
    "brown": {},
    "wind": {"gust_rate": 0.15, "gust_depth": 0.7, "tonal": 0.15},
    "crickets": {"n_insects": 6, "carrier": 4500.0, "pulse_rate": 32.0, "chirp_rate": 2.2, "detune": 0.06},
    "water": {"density": 2500.0, "rumble": 0.35, "size_min_mm": 0.7, "size_max_mm": 5.0},
    "rain": {"intensity": 0.5},
    "leaves": {"gust_rate": 0.2, "rate": 140.0},
}


def _rng(seed, k=0):
    return np.random.default_rng(np.random.SeedSequence([int(seed), int(k)]))


def _norm(x):
    r = np.sqrt(np.mean(x * x))
    return x / r if r > 0 else x


# ------------------------------------------------------------ coloured noise
def coloured_noise(n, beta, rng, fs):
    """Noise with power spectrum ~ 1/f^beta (0 white, 1 pink, 2 brown), FFT synthesis, unit RMS."""
    nfft = int(2 ** np.ceil(np.log2(n)))
    f = np.fft.rfftfreq(nfft, 1 / fs)
    amp = np.zeros_like(f)
    amp[1:] = f[1:] ** (-beta / 2)
    amp[0] = 0.0
    if beta > 0:  # flatten below 10 Hz to avoid unbounded drift
        amp[(f > 0) & (f < 10)] = (10.0 ** (-beta / 2))
    spec = amp * (rng.standard_normal(len(f)) + 1j * rng.standard_normal(len(f)))
    x = np.fft.irfft(spec, nfft)[:n]
    return _norm(x - x.mean())


def slow_process(n, fs, rate_hz, rng, sigma=1.0):
    """Smooth zero-mean random process with ~rate_hz bandwidth (unit std * sigma)."""
    if rate_hz <= 0:
        return np.zeros(n)
    m = max(8, int(n * rate_hz / fs * 4) + 8)
    pts = rng.standard_normal(m)
    t_src = np.linspace(0, 1, m)
    t = np.linspace(0, 1, n)
    from scipy.interpolate import CubicSpline
    y = CubicSpline(t_src, pts)(t)
    y = (y - y.mean()) / (y.std() + 1e-12)
    return sigma * y


def lognormal_modulator(n, fs, rate_hz, depth_db, rng):
    """Multiplicative gain whose dB-level fluctuates with std ``depth_db`` at ~rate_hz; unit mean power."""
    g_db = slow_process(n, fs, rate_hz, rng, depth_db)
    g = 10 ** (g_db / 20)
    return g / np.sqrt(np.mean(g * g))


# ----------------------------------------------------------- source models
def gen_wind(n, fs, rng, gust_rate=0.15, gust_depth=0.7, tonal=0.15, **_):
    base = coloured_noise(n, 1.6, rng, fs)
    sos = signal.butter(2, 1200, "low", fs=fs, output="sos")
    base = signal.sosfilt(sos, base)
    mid = signal.sosfilt(signal.butter(2, [300, 1500], "band", fs=fs, output="sos"), rng.standard_normal(n))
    g1 = lognormal_modulator(n, fs, gust_rate, 6.0 * gust_depth, rng)
    g2 = lognormal_modulator(n, fs, gust_rate * 2.0, 4.0 * gust_depth, rng)
    x = _norm(base) * g1 + 0.35 * _norm(mid) * g2
    if tonal > 0:  # soft, wandering edge-tone whistle
        f0 = 380 + 120 * slow_process(n, fs, 0.1, rng)
        ph = 2 * np.pi * np.cumsum(f0) / fs
        x = x + tonal * 0.5 * np.sin(ph) * np.clip(g1 - 1.0, 0, None)
    return _norm(x)


def gen_crickets(n, fs, rng, n_insects=6, carrier=4500.0, pulse_rate=32.0, chirp_rate=2.2, detune=0.06, **_):
    t = np.arange(n) / fs
    out = np.zeros(n)
    for k in range(int(max(1, n_insects))):
        fc = carrier * (1 + detune * rng.uniform(-1, 1))
        pr = pulse_rate * (1 + 0.1 * rng.uniform(-1, 1))
        cr = chirp_rate * (1 + 0.15 * rng.uniform(-1, 1))
        ph0 = rng.uniform(0, 2 * np.pi)
        # chirp envelope: ~ 35 % duty burst of pulses repeating at chirp_rate
        chirp_phase = (t * cr + rng.uniform()) % 1.0
        chirp_env = (chirp_phase < 0.38).astype(float)
        pulse = 0.5 * (1 - np.cos(2 * np.pi * (t * pr + rng.uniform()))) ** 1.5
        env = signal.sosfilt(signal.butter(2, 160, "low", fs=fs, output="sos"), chirp_env * pulse)
        wobble = 1 + 0.004 * slow_process(n, fs, 0.8, rng)
        car = np.sin(2 * np.pi * fc * np.cumsum(wobble) / fs + ph0) + 0.12 * np.sin(2 * np.pi * 2 * fc * np.cumsum(wobble) / fs)
        dist = 10 ** (rng.uniform(-6, 0) / 20)  # individual distance spread
        out += dist * env * car
    out *= lognormal_modulator(n, fs, 0.08, 2.0, rng)
    return _norm(out)


def _add_events(buf, starts, kernels):
    for s, k in zip(starts, kernels):
        e = min(len(buf), s + len(k))
        if e > s:
            buf[s:e] += k[: e - s]


def gen_water(n, fs, rng, density=2500.0, rumble=0.35, size_min_mm=0.7, size_max_mm=5.0, **_):
    """Stream: Poisson cloud of rising-frequency Minnaert bubble resonances plus low rumble."""
    dur = n / fs
    ne = int(density * dur)
    starts = rng.integers(0, n, ne)
    r = np.exp(rng.uniform(np.log(size_min_mm), np.log(size_max_mm), ne)) * 1e-3  # bubble radius, m
    f0 = 3.26 / r  # Minnaert: f ~ 3.26 / r (Hz, r in m)
    amps = r * 1e3 * rng.uniform(0.3, 1.0, ne)
    buf = np.zeros(n + 4000)
    lt = np.arange(int(0.03 * fs)) / fs
    for s, f, a in zip(starts, f0, amps):
        decay = 0.043 * f ** -0 * 1.0
        tau = 0.0006 * (f0.mean() / f) + 0.004  # decay constant ~ 4-6 ms
        k = a * np.exp(-lt / tau) * np.sin(2 * np.pi * (f + 0.1 * f * lt * 80) * lt)  # slight upward chirp
        e = min(len(buf), s + len(k))
        buf[s:e] += k[: e - s]
    x = buf[:n]
    x = _norm(x)
    rum = signal.sosfilt(signal.butter(2, [60, 500], "band", fs=fs, output="sos"), rng.standard_normal(n))
    x = x + rumble * _norm(rum)
    x *= lognormal_modulator(n, fs, 0.3, 1.5, rng)
    return _norm(x)


def gen_rain(n, fs, rng, intensity=0.5, **_):
    """Rain: dense droplet impacts (short band-limited noise bursts, 1.5-9 kHz) on a broadband bed."""
    rate = 400 + 3600 * float(np.clip(intensity, 0, 1)) ** 1.4
    ne = int(rate * n / fs)
    starts = rng.integers(0, n, ne)
    amps = rng.pareto(2.5, ne) + 0.3
    buf = np.zeros(n + 2000)
    for s, a in zip(starts, amps):
        L = int(rng.uniform(0.0008, 0.004) * fs)
        k = a * rng.standard_normal(L) * np.exp(-np.arange(L) / (L / 3.0))
        buf[s:s + L] += k
    x = buf[:n]
    sos = signal.butter(2, [1500, min(9000, fs / 2 * 0.95)], "band", fs=fs, output="sos")
    x = signal.sosfilt(sos, x)
    bed = signal.sosfilt(signal.butter(2, [800, 7000], "band", fs=fs, output="sos"), rng.standard_normal(n))
    x = _norm(x) + (0.35 + 0.4 * intensity) * _norm(bed)
    x *= lognormal_modulator(n, fs, 0.2, 1.0 + 2.0 * (1 - intensity), rng)
    return _norm(x)


def gen_leaves(n, fs, rng, gust_rate=0.2, rate=140.0, **_):
    """Foliage rustle: crackle events (high-passed clicks) whose rate follows slow wind gusts."""
    gust = np.clip(1.0 + 0.9 * slow_process(n, fs, gust_rate, rng), 0.02, None) ** 2
    lam = rate * gust / fs
    ev = rng.random(n) < lam
    idx = np.nonzero(ev)[0]
    buf = np.zeros(n + 800)
    for s in idx:
        L = int(rng.uniform(0.0004, 0.0025) * fs)
        k = rng.standard_normal(L) * np.exp(-np.arange(L) / (L / 2.5)) * rng.pareto(3.0) * 0.8 + 0
        buf[s:s + L] += k * (1 + 0.5 * rng.standard_normal())
    x = buf[:n]
    x = signal.sosfilt(signal.butter(2, [2000, min(10000, fs / 2 * 0.95)], "band", fs=fs, output="sos"), x)
    hiss = signal.sosfilt(signal.butter(2, [3000, 9000], "band", fs=fs, output="sos"), rng.standard_normal(n)) * np.sqrt(gust) * 0.15
    x = _norm(x) + _norm(hiss) * 0.3
    return _norm(x)


_GEN = {
    "white": lambda n, fs, r, **p: coloured_noise(n, 0.0, r, fs),
    "pink": lambda n, fs, r, **p: coloured_noise(n, 1.0, r, fs),
    "brown": lambda n, fs, r, **p: coloured_noise(n, 2.0, r, fs),
    "wind": gen_wind, "crickets": gen_crickets, "water": gen_water, "rain": gen_rain, "leaves": gen_leaves,
}


# ------------------------------------------------------- shaping and levels
def apply_shaping(x, fs, eq=None):
    """Zero-phase spectral shaping. eq = {"tilt_db_oct": float, "lowcut": Hz, "highcut": Hz,
    "bands": {fc_hz(str|float): gain_dB}} (third-octave band gains, interpolated in log-f)."""
    if not eq:
        return x
    n = len(x)
    nfft = int(2 ** np.ceil(np.log2(n)))
    X = np.fft.rfft(x, nfft)
    f = np.fft.rfftfreq(nfft, 1 / fs)
    g_db = np.zeros_like(f)
    tilt = float(eq.get("tilt_db_oct", 0.0))
    if tilt:
        g_db += tilt * np.log2(np.maximum(f, 20.0) / 1000.0)
    bands = eq.get("bands") or {}
    if bands:
        fc = np.array(sorted(float(k) for k in bands))
        gv = np.array([float(bands[k]) if k in bands else float(bands[str(k)]) for k in
                       sorted(bands, key=lambda k: float(k))])
        g_db += np.interp(np.log2(np.maximum(f, 1.0)), np.log2(fc), gv, left=gv[0], right=gv[-1])
    g = 10 ** (g_db / 20)
    lc, hc = eq.get("lowcut"), eq.get("highcut")
    if lc:
        g *= 1 / np.sqrt(1 + (lc / np.maximum(f, 1e-3)) ** 8)
    if hc:
        g *= 1 / np.sqrt(1 + (np.maximum(f, 1e-3) / hc) ** 8)
    y = np.fft.irfft(X * g, nfft)[:n]
    return y


def apply_temporal(x, fs, mod, rng):
    """mod = {"depth_db": std of slow level fluctuation, "rate_hz": ..., "am_depth": 0-1, "am_hz": ...}."""
    if not mod:
        return x
    y = x
    if mod.get("depth_db", 0) > 0:
        y = y * lognormal_modulator(len(y), fs, float(mod.get("rate_hz", 0.2)), float(mod["depth_db"]), rng)
    if mod.get("am_depth", 0) > 0:
        t = np.arange(len(y)) / fs
        y = y * (1 + float(mod["am_depth"]) * np.sin(2 * np.pi * float(mod.get("am_hz", 4.0)) * t))
    return y


def set_level(x, fs, level_db, weighting="A"):
    """Scale a signal (any units) to the requested Leq/LAeq in dB re 20 uPa -> returns Pa."""
    cur = U.laeq(x, fs) if weighting.upper() == "A" else U.leq(x)
    if not np.isfinite(cur) or cur < -200:
        return x * 0.0
    return x * 10 ** ((level_db - cur) / 20)


def render_component(spec: dict, duration_s: float, fs: int = FS_DEFAULT, seed: int = 1, k: int = 0):
    """spec = {type, level, weighting('A'|'Z'), params{}, eq{}, mod{}, mute?}. Returns Pa, length duration*fs."""
    typ = spec["type"]
    if typ not in _GEN:
        raise ValueError(f"unknown masker type {typ}")
    n = int(round(duration_s * fs))
    rng = _rng(seed, k)
    p = dict(DEFAULT_PARAMS.get(typ, {}))
    p.update(spec.get("params") or {})
    x = _GEN[typ](n, fs, rng, **p)
    x = apply_shaping(x, fs, spec.get("eq"))
    x = apply_temporal(x, fs, spec.get("mod"), _rng(seed, 1000 + k))
    # short fades avoid edge clicks
    nf = min(n // 2, int(0.02 * fs))
    if nf > 1:
        w = np.linspace(0, 1, nf)
        x[:nf] *= w
        x[-nf:] *= w[::-1]
    return set_level(x, fs, float(spec.get("level", 40.0)), spec.get("weighting", "A"))


def render_scene(components: list[dict], duration_s: float, fs: int = FS_DEFAULT, seed: int = 1):
    """Sum of components (each at its own receiver level). Returns (Pa signal, per-component list)."""
    n = int(round(duration_s * fs))
    total = np.zeros(n)
    parts = []
    for k, c in enumerate(components):
        if c.get("mute"):
            continue
        s = render_component(c, duration_s, fs, seed, k)
        total += s
        parts.append(s)
    return total, parts


def custom_masker(x, fs_in, fs, duration_s, level=None, weighting="A", seed=1, loop=True):
    """Prepare an uploaded masker WAV (Pa or relative): resample, loop/cut to duration, optionally rescale."""
    from .audio_io import resample
    y = resample(x, fs_in, fs)
    n = int(round(duration_s * fs))
    if len(y) < n:
        if not loop:
            y = np.pad(y, (0, n - len(y)))
        else:  # cross-faded looping to avoid clicks
            reps = int(np.ceil(n / len(y))) + 1
            xf = min(len(y) // 8, int(0.05 * fs))
            out = y.copy()
            ramp = np.linspace(0, 1, max(xf, 1))
            while len(out) < n + 1:
                out = np.concatenate([out[:-xf] if xf else out, np.concatenate([out[-xf:] * ramp[::-1] + y[:xf] * ramp, y[xf:]]) if xf else y])
            y = out
    y = y[:n]
    if level is not None:
        y = set_level(y, fs, level, weighting)
    return y


# ================================================== synthetic industrial targets
TARGET_KINDS = {
    "hammer": "Hammering (metal impacts, 1.8/s)",
    "drill": "Percussion drilling (rotary hammer)",
    "jackhammer": "Jackhammer (20 impacts/s)",
    "grinder": "Angle grinder (broadband + tones)",
}


def synth_target(kind: str, duration_s: float = 4.0, fs: int = FS_DEFAULT, seed: int = 1, level_dba: float = 60.0):
    """Synthetic industrial source as received at the nominal distance (Pa). SYNTHETIC: for demonstrations and
    tests only; replace by a real calibrated recording for any engineering conclusion."""
    rng = _rng(seed, 900)
    n = int(duration_s * fs)
    t = np.arange(n) / fs
    x = np.zeros(n)
    if kind == "hammer":
        times = np.cumsum(rng.uniform(0.4, 0.7, 40))
        times = times[times < duration_s - 0.3]
        modes = np.array([1250, 2310, 3560, 5120, 6880]) * rng.uniform(0.97, 1.03, 5)
        for t0 in times:
            i = int(t0 * fs)
            L = min(n - i, int(0.3 * fs))
            tt = np.arange(L) / fs
            a = rng.uniform(0.6, 1.0)
            click = rng.standard_normal(L) * np.exp(-tt / 0.0012)
            ring = sum(np.sin(2 * np.pi * f * tt) * np.exp(-tt / d) * w for f, d, w in zip(modes, [0.07, 0.05, 0.035, 0.025, 0.015], [1, .7, .5, .35, .2]))
            thump = np.sin(2 * np.pi * 160 * tt) * np.exp(-tt / 0.012) * 0.8
            x[i:i + L] += a * (0.8 * click + 0.5 * ring + thump)
    elif kind == "jackhammer":
        rate = 20.0
        times = np.arange(0.05, duration_s - 0.1, 1 / rate) + rng.normal(0, 0.002, int((duration_s - 0.15) * rate) + 1)[: len(np.arange(0.05, duration_s - 0.1, 1 / rate))]
        for t0 in times:
            i = int(t0 * fs)
            L = min(n - i, int(0.04 * fs))
            if L <= 0:
                continue
            tt = np.arange(L) / fs
            x[i:i + L] += rng.uniform(0.7, 1.0) * (np.sin(2 * np.pi * 220 * tt) * np.exp(-tt / 0.01) + 0.6 * rng.standard_normal(L) * np.exp(-tt / 0.004))
        x = x + 0.15 * signal.sosfilt(signal.butter(2, [100, 3000], "band", fs=fs, output="sos"), rng.standard_normal(n))
    elif kind == "drill":
        f0 = 95.0
        for h in range(1, 30):
            x += (1.0 / h ** 1.1) * np.sin(2 * np.pi * f0 * h * t + rng.uniform(0, 6.28))
        pulse = 0.5 * (1 + np.sign(np.sin(2 * np.pi * 42.0 * t))) * np.exp(-((t * 42.0) % 1.0) * 6)
        band = signal.sosfilt(signal.butter(2, [1200, 5500], "band", fs=fs, output="sos"), rng.standard_normal(n))
        x = 0.5 * x + 1.6 * pulse * band / band.std() + 0.4 * np.sin(2 * np.pi * (2700 + 150 * np.sin(2 * np.pi * 0.3 * t)) * t)
    elif kind == "grinder":
        band = signal.sosfilt(signal.butter(3, [1500, 9000], "band", fs=fs, output="sos"), rng.standard_normal(n))
        x = band / band.std() + 0.5 * np.sin(2 * np.pi * 4100 * t) + 0.25 * np.sin(2 * np.pi * 8200 * t) + 0.3 * np.sin(2 * np.pi * 280 * t)
        x *= 1 + 0.15 * np.sin(2 * np.pi * 1.5 * t)
    else:
        raise ValueError(kind)
    nf = int(0.02 * fs)
    x[:nf] *= np.linspace(0, 1, nf); x[-nf:] *= np.linspace(1, 0, nf)
    return set_level(x, fs, level_dba, "A")
