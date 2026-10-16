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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"\n{len(tests)} EME tests passed.")
