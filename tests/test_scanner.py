import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scanner"))
import alerts  # noqa: E402
import profit  # noqa: E402
import saleinfo  # noqa: E402
import rules as rules_mod  # noqa: E402
from textutil import contains_all, contains_any  # noqa: E402

S = Path(__file__).resolve().parent.parent / "scanner"
CFG = yaml.safe_load((S / "config.yaml").read_text(encoding="utf-8"))
RULES = yaml.safe_load((S / "rules.yaml").read_text(encoding="utf-8"))


def test_ems_bands_and_2027_switch():
    sh = CFG["shipping"]
    assert profit.ems_rate(sh, 4, 450, date(2026, 10, 27)) == 3900
    assert profit.ems_rate(sh, 4, 1000, date(2026, 10, 27)) == 5300
    assert profit.ems_rate(sh, 3, 1100, date(2026, 10, 27)) == 5000
    # new table from 1 Feb 2027: lightest band is 1 kg
    assert profit.ems_rate(sh, 4, 450, date(2027, 2, 1)) == 7400
    assert profit.ems_rate(sh, 3, 2500, date(2027, 3, 1)) == 10100
    assert profit.ems_rate(sh, 4, 99999, date(2026, 10, 27)) is None


def test_compute_matches_hand_calculation():
    d = {"zone": 4, "duty": 0.125}
    sale_jpy, per_order = 15000.0, 60.0
    r = profit.compute(10000, True, sale_jpy, d, 900, "pedal", CFG, per_order, points_jpy=500,
                       on=date(2026, 10, 27))
    e = CFG["ebay"]
    fee = (sale_jpy * (e["final_value_fee"] + e["international_fee"]) + per_order) * (1 + e["fee_tax"])
    rev = sale_jpy * (1 - CFG["fx"]["conversion_cost"])
    expected = rev - fee - 5020 - sale_jpy * 0.125 - (10000 - 500) - CFG["costs"]["packaging_jpy"]
    assert abs(r["profit_jpy"] - expected) <= 1
    r2 = profit.compute(10000, False, sale_jpy, d, 900, "pedal", CFG, per_order, points_jpy=500,
                        on=date(2026, 10, 27))
    assert r["profit_jpy"] - r2["profit_jpy"] == CFG["costs"]["rakuten_domestic_postage_jpy"]


def test_points_on_tax_excluded_price():
    cfgp = {"enabled": True, "extra_rate_pct": 2, "point_value_jpy": 1.0}
    assert profit.points_value(11000, 1, cfgp) == 300          # 10,000 ex-tax × 3%
    assert profit.points_value(11000, 10, {"enabled": False}) == 0


def test_sale_windows():
    from datetime import datetime
    JST = saleinfo.JST
    s = CFG["sales"]
    assert saleinfo.current(s, datetime(2026, 12, 4, 21, 0, tzinfo=JST))["name"].startswith("楽天スーパーSALE")
    assert saleinfo.current(s, datetime(2026, 12, 4, 19, 0, tzinfo=JST)) is None
    assert saleinfo.current(s, datetime(2026, 12, 11, 1, 30, tzinfo=JST)) is not None
    assert saleinfo.upcoming(s, datetime(2026, 12, 12, tzinfo=JST))["start"].month == 3


def test_alert_selection_dedupes_and_thresholds():
    a = {"min_profit_jpy": 5000, "min_margin": 0.15, "max_per_run": 5, "realert_if_profit_up": 0.2}
    mk = lambda i, p, m, warn=None: {"id": i, "best": {"profit_jpy": p, "margin": m, "country": "US"},  # noqa: E731
                                     "warnings": warn or []}
    opps = [mk("a", 9000, 0.3), mk("b", 3000, 0.3), mk("c", 9000, 0.1),
            mk("d", 9000, 0.3, [{"level": "block", "text": "alcohol"}]), mk("e", 9000, 0.3)]
    state = {"e": {"profit_jpy": 8500, "at": "2026-10-27T00:00:00+00:00"}}
    assert [o["id"] for o in alerts.pick(opps, a, state)] == ["a"]
    state["e"]["profit_jpy"] = 7000   # profit rose 28% since last alert -> alert again
    assert {o["id"] for o in alerts.pick(opps, a, state)} == {"a", "e"}


def test_matching_ignores_fullwidth_and_case():
    assert contains_all("ＢＯＳＳ　ＳＤ－１Ｗ 技", ["sd-1w"])
    assert contains_any("Misono UX10 210mm", [210])


def test_knife_blocked_for_uk_and_keyword_flags():
    item = {"category": "knife"}
    warns, blocked = rules_mod.warnings_for(item, "包丁 電池付 並行輸入", None, RULES, ["US", "GB"])
    assert "GB" in blocked
    texts = " ".join(w["text"] for w in warns)
    assert "battery" in texts and "parallel import" in texts


def test_id_check_categories():
    warns, _ = rules_mod.warnings_for({"category": "game"}, "ゲーム", None, RULES, [])
    assert any("ANY price" in w["text"] for w in warns)
