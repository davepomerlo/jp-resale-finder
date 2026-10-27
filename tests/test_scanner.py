import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scanner"))
import profit  # noqa: E402
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
    r = profit.compute(10000, True, 100.0, 150.0, d, 900, "pedal", CFG, on=date(2026, 10, 27))
    e = CFG["ebay"]
    fee = (100 * (e["final_value_fee"] + e["international_fee"]) + e["per_order_fee_usd"]) * (1 + e["fee_tax"]) * 150
    rev = 100 * 150 * (1 - CFG["fx"]["conversion_cost"])
    expected = rev - fee - 5020 - 100 * 150 * 0.125 - 10000 - CFG["costs"]["packaging_jpy"]
    assert abs(r["profit_jpy"] - expected) <= 1
    # postage not included adds the domestic postage cost
    r2 = profit.compute(10000, False, 100.0, 150.0, d, 900, "pedal", CFG, on=date(2026, 10, 27))
    assert r["profit_jpy"] - r2["profit_jpy"] == CFG["costs"]["rakuten_domestic_postage_jpy"]


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
