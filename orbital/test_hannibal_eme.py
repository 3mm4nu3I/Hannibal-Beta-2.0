"""Offline tests for the EME link budget (hannibal_eme). No network. Run: python test_hannibal_eme.py"""
import math

import hannibal_eme as e

MEAN_KM = 384400.0


def approx(a, b, tol):
    assert abs(a - b) <= tol, f"{a} != {b} (tol {tol})"


def test_path_loss_between_isotropic():
    # The textbook EME figures at the mean Earth-Moon distance.
    approx(e.path_loss_db(144e6, MEAN_KM), 252.0, 1.0)
    approx(e.path_loss_db(1296e6, MEAN_KM), 271.0, 1.0)
    # Path loss grows with frequency (shorter lambda) for isotropic antennas.
    assert e.path_loss_db(1296e6, MEAN_KM) > e.path_loss_db(144e6, MEAN_KM)
    # ... and with the 4th power of range: +6 dB per doubling.
    approx(e.path_loss_db(144e6, 2 * MEAN_KM) - e.path_loss_db(144e6, MEAN_KM), 12.04, 0.05)


def test_dish_gain():
    approx(e.dish_gain_dbi(3.0, 1296e6, 0.55), 29.6, 0.3)       # 3 m at 23 cm ~ 30 dBi
    # Fixed dish: gain rises ~6 dB per octave of frequency (G ~ f^2).
    approx(e.dish_gain_dbi(3.0, 2592e6, 0.55) - e.dish_gain_dbi(3.0, 1296e6, 0.55), 6.02, 0.05)


def test_doppler_sign_and_scale():
    # Receding (+range-rate) -> echo returns LOWER (negative shift).
    assert e.two_way_doppler_hz(1296e6, +0.2) < 0
    assert e.two_way_doppler_hz(1296e6, -0.2) > 0
    approx(e.two_way_doppler_hz(1296e6, 0.2118), -1831.0, 5.0)
    approx(e.two_way_doppler_hz(144e6, 0.2118), -203.0, 2.0)


def test_round_trip_and_depth():
    approx(e.round_trip_s(MEAN_KM), 2.56, 0.02)
    approx(e.echo_depth_ms(), 11.6, 0.2)


def test_noise_and_processing_gain():
    approx(e.noise_density_dbm_hz(100.0), -178.6, 0.2)
    approx(e.processing_gain_db(2500.0, 60.0), 51.8, 0.1)
    # Noise rises 10 dB per decade of bandwidth.
    approx(e.noise_power_dbm(100, 25000) - e.noise_power_dbm(100, 2500), 10.0, 0.01)


def test_link_budget_verdict_flips():
    # A capable 23 cm station hears its echo (digital); a single 2 m yagi does not.
    big = e.link_budget(1296e6, MEAN_KM, 0.0, pt_w=300, dish_m=3.0, t_sys_k=100)
    assert big["best_mode"] is not None and "echo detectable" in big["verdict"]
    tiny = e.link_budget(144e6, MEAN_KM, 0.0, pt_w=100, g_tx_dbi=14, g_rx_dbi=14, t_sys_k=300, dish_m=1)
    assert tiny["best_mode"] is None and "below" in tiny["verdict"]
    # More transmit power raises received power dB-for-dB.
    hotter = e.link_budget(1296e6, MEAN_KM, 0.0, pt_w=3000, dish_m=3.0, t_sys_k=100)
    approx(hotter["pr_dbm"] - big["pr_dbm"], 10.0, 0.01)


def test_sky_noise_by_band():
    # Galactic background: ~200 K at 2 m away from the Milky Way, thousands on 6 m, a few K on 23 cm.
    approx(e.sky_temp_k(144e6), 202.7, 0.1)
    assert e.sky_temp_k(50.2e6) > 2000
    assert e.sky_temp_k(1296.1e6) < 5
    # It falls as f^-2.55 (plus the 2.7 K background).
    approx((e.sky_temp_k(72e6) - e.T_CMB_K) / (e.sky_temp_k(144e6) - e.T_CMB_K), 2 ** 2.55, 0.01)


def test_yagi_array_gain():
    approx(e.yagi_array_gain_dbi(15.0, 1), 15.0, 1e-9)                  # one Yagi: no phasing loss
    approx(e.yagi_array_gain_dbi(15.0, 2), 15.0 + 3.01 - 0.5, 0.01)
    approx(e.yagi_array_gain_dbi(15.0, 4), 15.0 + 6.02 - 0.5, 0.01)
    approx(e.antenna_gain_dbi({"type": "yagi", "gain_dbi": 15.0, "count": 4}, 144e6), 20.52, 0.01)


def test_dish_kinds():
    prime = e.antenna_gain_dbi({"type": "dish", "kind": "prime-focus", "diameter_m": 3.0}, 1296e6)
    offset = e.antenna_gain_dbi({"type": "dish", "kind": "offset", "diameter_m": 3.0}, 1296e6)
    mesh = e.antenna_gain_dbi({"type": "dish", "kind": "mesh", "diameter_m": 3.0}, 1296e6)
    approx(prime, e.dish_gain_dbi(3.0, 1296e6, 0.55), 1e-9)              # same as before for the default kind
    assert mesh < prime < offset
    # An explicit efficiency still wins over the kind's typical value.
    approx(e.antenna_gain_dbi({"type": "dish", "kind": "mesh", "diameter_m": 3.0, "efficiency": 0.55}, 1296e6),
           prime, 1e-9)


def test_antenna_answers():
    assert e.parse_antenna_answer("", "yagi") == ("yagi", None)
    assert e.parse_antenna_answer("D", "yagi") == ("dish", None)
    assert e.parse_antenna_answer("yagi", "dish") == ("yagi", None)
    assert e.parse_antenna_answer("3", "yagi") == ("dish", 3.0)          # RUN_EME.bat answers '3' here
    for bad in ("banana", "-2", "0"):
        try:
            e.parse_antenna_answer(bad, "dish")
            raise AssertionError(f"accepted {bad!r}")
        except ValueError:
            pass


def test_system_noise_by_band_and_antenna():
    yagi = {"type": "yagi", "gain_dbi": 15.0, "count": 4}
    t2m, parts = e.system_temp_k(144.1e6, yagi, e.antenna_gain_dbi(yagi, 144.1e6))
    assert 250 < t2m < 300 and parts["sky"] > parts["receiver"]          # 2 m: the sky dominates
    dish = {"type": "dish", "kind": "prime-focus", "diameter_m": 3.0}
    t23, parts23 = e.system_temp_k(1296.1e6, dish, e.antenna_gain_dbi(dish, 1296.1e6))
    assert 55 < t23 < 75 and parts23["ground"] == 20.0                   # 23 cm: receiver + spillover
    offset = dict(dish, kind="offset")
    assert e.system_temp_k(1296.1e6, offset, 30.0)[1]["ground"] == 10.0
    # 3 cm with a 3 m dish: the Moon fills much of the beam and its own glow adds tens of kelvin.
    assert e.system_temp_k(10368.1e6, dish, e.antenna_gain_dbi(dish, 10368.1e6))[1]["moon"] > 50
    # A fixed 100 K made 2 m look several dB better than it is.
    g = e.antenna_gain_dbi(yagi, 144.1e6)
    old = e.link_budget(144.1e6, MEAN_KM, 0.0, pt_w=300, dish_m=1, g_tx_dbi=g, g_rx_dbi=g, t_sys_k=100)
    new = e.link_budget(144.1e6, MEAN_KM, 0.0, pt_w=300, dish_m=1, g_tx_dbi=g, g_rx_dbi=g, t_sys_k=t2m)
    approx(old["snr_ref_db"] - new["snr_ref_db"], 10 * math.log10(t2m / 100), 0.01)


def test_defaults_per_band():
    assert e.antenna_defaults("2m")["type"] == "yagi" and e.antenna_defaults("2m")["yagi_dbi"] == 15.0
    assert e.antenna_defaults("6m")["yagi_dbi"] == 12.0
    assert e.antenna_defaults("23cm")["type"] == "dish"
    assert e.default_antenna("23cm") == {"type": "dish", "kind": "prime-focus", "diameter_m": 3.0, "efficiency": None}
    assert e.station_defaults()["t_sys_k"] is None                       # auto unless HANNIBAL_EME_TSYS_K is set


# ---- the [E] screen, with the Moon stubbed out (no network) ---------------------------------------
MOON = {"az": 120.0, "el": 30.0, "range_km": MEAN_KM, "range_rate_kms": 0.1, "as_of": "2026-Oct-23 16:00",
        "stale": False, "home": {"lat": 51.2194, "lon": 4.4025, "alt_km": 0.01, "name": "Antwerp", "set": True}}


def run_screen(answers):
    import hannibal_orbital as ho
    real, e.current_moon = e.current_moon, (lambda *a, **k: dict(MOON))
    it, out = iter(answers), []
    try:
        ho.screen_eme(lambda prompt, default="": (next(it, "").strip() or default), out.append, False)
    finally:
        e.current_moon = real
    return "\n".join(out)


def test_screen_keeps_run_eme_bat_working():
    # RUN_EME.bat pipes exactly these four answers: band, dish diameter, power, Tsys.
    text = run_screen(["23cm", "3", "300", "100"])
    assert "3.0 m prime-focus dish @ 55%" in text and "Tsys 100 K, set by you" in text
    old = e.link_budget(e.BANDS["23cm"], MEAN_KM, 0.1, pt_w=300, dish_m=3.0, t_sys_k=100)
    assert f"SNR in 2500 Hz reference: {old['snr_ref_db']:+.1f} dB" in text       # identical to the old model
    assert "NOT added to the SNR" in text


def test_screen_yagi_and_auto_noise():
    text = run_screen(["2m", "y", "15", "4", "300", ""])
    assert "4 x 15.0 dBi Yagis" in text and "auto = receiver 40 + sky 202 + moon 0 + ground 30" in text
    text = run_screen(["2m", "d", "offset", "10", "300", ""])
    assert "10.0 m offset dish @ 65%" in text and "rather than a dish" in text
    text = run_screen(["23cm", "banana", "", "", ""])
    assert "Using the defaults for this band" in text and "3.0 m prime-focus dish" in text
    text = run_screen(["23cm", "3", "-5", ""])                          # no crash on a negative power
    assert "Using the defaults for this band" in text and "Tx 300 W" in text


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"\n{len(tests)} EME tests passed.")
