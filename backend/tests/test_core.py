"""Numerical validation of the building blocks (units, calibration, filters, generators, fast model, staircase)."""
import numpy as np, pytest
from aml import units as U, audio_io as A, generators as G, spectra as SP, fastmodel as F, experiments as E, optimize as O, loudness as LD

FS = 32000


def test_level_arithmetic():
    assert abs(U.dbsum([60, 60]) - 63.0103) < 1e-3
    x = np.sqrt(2) * 1.0 * np.sin(2 * np.pi * 1000 * np.arange(FS) / FS)      # 1 Pa rms
    assert abs(U.leq(x) - 93.979) < 0.01                                         # 94 dB


def test_a_weighting_iec_table():
    for f, v in [(63, -26.2), (125, -16.1), (250, -8.6), (500, -3.2), (1000, 0.0), (2000, 1.2), (4000, 1.0), (8000, -1.1)]:
        assert abs(U.a_weight_db(f) - v) < 0.1
    x = np.sin(2 * np.pi * 125 * np.arange(2 * FS) / FS)
    assert abs(U.laeq(x, FS) - U.leq(x) - (-16.1)) < 0.2


def test_calibration_modes():
    t = np.arange(FS) / FS
    raw = 0.1 * np.sin(2 * np.pi * 1000 * t)
    y, g = A.apply_calibration(raw, FS, A.Calibration("calibrator", 94.0, 0.0, 1.0))
    assert abs(U.leq(y) - 94.0) < 0.1
    y, g = A.apply_calibration(raw, FS, A.Calibration("known_level", 70.0))
    assert abs(U.leq(y) - 70.0) < 0.01
    y, g = A.apply_calibration(raw, FS, A.Calibration("fullscale_pa", 10.0))
    assert abs(np.max(np.abs(y)) - 1.0) < 1e-9


def test_third_octave_sum_equals_total():
    # white noise band-limited to 100 Hz - 10 kHz: the 1/3-octave bands 80 Hz - 12.5 kHz must add up to the total
    x = G.render_component({"type": "white", "level": 60, "weighting": "Z"}, 8, FS, 3)
    x = G.apply_shaping(x, FS, {"lowcut": 100.0, "highcut": 10000.0})
    c = U.third_octave_centres(63, 12500)
    L = SP.third_octave_levels(x, FS, c)
    assert abs(U.dbsum(L[np.isfinite(L)]) - U.leq(x)) < 0.4


def test_propagation_spherical():
    x = np.random.default_rng(1).standard_normal(FS)
    y = U.propagate(x, FS, 7, 14, atmosphere=False)
    assert abs(U.leq(y) - U.leq(x) + 6.02) < 0.01


def test_atmospheric_absorption_iso_table():
    # ISO 9613-2:1996 Table 2, 20 C / 70 % RH, octave-band midpoints (exact IEC 61260 centres), dB/km
    table = [0.1, 0.3, 1.1, 2.8, 5.0, 9.0, 22.9, 76.6]
    f = U.exact_centres(np.array([63, 125, 250, 500, 1000, 2000, 4000, 8000.0]), 1)
    assert np.allclose(U.alpha_iso9613_1(f, 20, 70) * 1000, table, atol=0.1 + 0.01 * np.array(table))


@pytest.mark.parametrize("typ", list(G.TYPES))
def test_generators_level_and_determinism(typ):
    a = G.render_component({"type": typ, "level": 45}, 3, FS, 5)
    b = G.render_component({"type": typ, "level": 45}, 3, FS, 5)
    assert np.array_equal(a, b) and np.isfinite(a).all()
    assert abs(U.laeq(a, FS) - 45) < 0.05


def test_pink_and_brown_octave_slopes():
    for typ, slope in (("pink", 0.0), ("brown", -3.0)):   # brown: PSD -6 dB/oct -> octave-band level -3 dB/oct
        x = G.render_component({"type": typ, "level": 60, "weighting": "Z"}, 20, FS, 1)
        L = SP.band_levels(x, FS, np.array([250.0, 500.0, 1000.0, 2000.0, 4000.0]), 1)
        assert abs(np.mean(np.diff(L)) - slope) < 0.8


def test_shaping_filter_bands():
    x = G.render_component({"type": "white", "level": 60, "weighting": "Z"}, 6, FS, 2)
    y = G.apply_shaping(x, FS, {"bands": {"500": -20, "1000": 0, "2000": 0}})
    L0 = SP.band_levels(x, FS, np.array([250.0, 2000.0]), 3)
    L1 = SP.band_levels(y, FS, np.array([250.0, 2000.0]), 3)
    assert L1[0] - L0[0] < -15 and abs(L1[1] - L0[1]) < 1


def _tone_in_noise(f, dur, seed=1):
    n = FS; t = np.arange(n) / FS
    N0 = U.P0 ** 2 * 10 ** 3.0
    noise = np.random.default_rng(seed).standard_normal(n) * np.sqrt(N0 * FS / 2)
    x = np.zeros(n); k = int(dur * FS); i0 = (n - k) // 2
    x[i0:i0 + k] = np.sin(2 * np.pi * f * t[i0:i0 + k]) * np.sqrt(2 * N0 * 10 ** 1.8)
    return x, noise


def test_fastmodel_critical_ratio_anchor():
    x, noise = _tone_in_noise(1000, 0.5)
    assert abs(F.analyse(x, noise, FS).solve(0.75, "target")) < 1.0   # CR 18 dB reproduces P = 0.75


def test_fastmodel_trends():
    thr = lambda f, d: F.analyse(*_tone_in_noise(f, d, 2), FS).solve(0.75, "target")
    assert thr(4000, 0.5) > thr(500, 0.5) + 3          # critical ratio grows with frequency
    assert thr(1000, 0.05) > thr(1000, 0.5) + 3        # temporal integration: shorter = harder
    t = np.arange(FS) / FS
    L = U.threshold_in_quiet_db(1000.0)
    x = np.sin(2 * np.pi * 1000 * t) * np.sqrt(2) * U.P0 * 10 ** (L / 20)
    assert 0.6 < F.analyse(x, np.zeros(FS), FS).p2afc() < 0.97   # tone at the absolute threshold


def test_forward_masking_decay():
    n = 2 * FS; t = np.arange(n) / FS
    m = np.random.default_rng(3).standard_normal(n) * 0.2
    m[FS:] *= 0.0001                                   # masker ends at 1 s
    probe = lambda t0: np.where((t > t0) & (t < t0 + 0.02), np.sin(2 * np.pi * 1000 * t) * 0.003, 0.0)
    assert F.analyse(probe(1.01), m, FS).p2afc() < F.analyse(probe(1.3), m, FS).p2afc()


def test_p2afc_mapping():
    assert abs(F.p2afc_from_dprime(0.0) - 0.5) < 1e-12
    assert abs(F.p2afc_from_dprime(F.dprime_from_p2afc(0.8)) - 0.8) < 1e-9


def test_staircase_converges_to_known_threshold():
    from scipy.stats import norm
    rng = np.random.default_rng(4)
    ths = []
    for k in range(8):
        st = E.Staircase(start=10.0, rule="2down1up", n_reversals=14)
        while not st.finished:
            st.update(E.simulate_listener(st.value, -10.0, 2.0, 0.0, rng))
        ths.append(st.threshold()[0])
    expect = -10.0 + 2.0 * norm.ppf((0.7071 - 0.5) / 0.5)      # 70.7 % point of the simulated listener
    assert abs(np.mean(ths) - expect) < 1.2


def test_psychometric_fit_recovers_parameters():
    rng = np.random.default_rng(5)
    x = np.repeat(np.array([-18, -14, -10, -6, -2.0]), 40)
    y = np.array([E.simulate_listener(v, -10.0, 3.0, 0.0, rng) for v in x])
    f = E.fit_psychometric(x, y, p_crit=0.75, n_boot=60)
    assert f["ok"] and abs(f["threshold"] + 10.0) < 1.5
    assert f["ci95"][0] < f["threshold"] < f["ci95"][1]


def test_band_partition_of_unity():
    f = np.linspace(20, 15000, 2000)
    assert np.allclose(O.band_weights(f, O.band_centres()).sum(axis=0), 1.0)


def test_optimiser_meets_criterion_and_not_worse_than_flat():
    from aml import service as S
    ws = S.Workspace(id="t"); ws.target_raw = G.synth_target("hammer", 1.5, FS, 1, 60); ws.fs_raw = FS; ws.prepare()
    m = ws.render_masker({"components": [{"type": "pink", "level": 40, "weighting": "A"}]}, 1.5, 3)
    res = O.optimise_shape(O.build_scene(ws.target_event, m, FS), 0.6, 0.0)
    assert res["ok"] and abs(res["P2AFC"] - 0.6) < 0.01
    assert res["LAeq"] <= res["flat"]["LAeq"] + 0.05


def test_loudness_reference_points():
    t = np.arange(FS) / FS
    x40 = np.sin(2 * np.pi * 1000 * t) * np.sqrt(2) * U.P0 * 10 ** (40 / 20)
    m40, m50 = LD.metrics(x40, FS), LD.metrics(x40 * 10 ** 0.5, FS)
    assert abs(m40["N5_sone"] - 1.0) < 0.1                       # definition of the sone
    assert 1.4 < m50["N5_sone"] / m40["N5_sone"] < 2.4           # roughly a doubling per 10 dB
