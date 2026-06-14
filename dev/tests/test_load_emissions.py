#!/usr/bin/env python3
"""Self-check for load_emissions CDU parsing. Run: python dev/tests/test_load_emissions.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "climate_data"))
from load_emissions import cdu_emission_rows, norm

HEADER = ["Company", "Latest year", "Scope 1", "Scope 2 (location-based)",
          "Total", "2026 projected", "helper", "2021", "2022"]


def test_norm():
    assert norm("AIRBUS SE") == "AIRBUS"           # legal suffix dropped
    assert norm("AXA Group") == "AXA"              # GROUP dropped
    assert norm("L'Oréal") == "L OREAL"            # accents stripped, punctuation -> space
    assert norm("FILIALE NV") == "FILIALE"         # NV token dropped as a legal suffix
    assert norm("STMICROELECTRONICS N.V.") == "STMICROELECTRONICS N V"  # "N.V." -> two tokens (still consistent both sides)
    print("ok: norm strips accents, punctuation, legal suffixes")


def test_cdu_rows():
    name2lei = {"ACME": "LEI_ACME", "STELLANTIS": "LEI_STLA"}
    rows = [
        ["Scope 1 & 2 …"], [],                      # 2 banner rows before header
        HEADER,
        ["ACME", "2022", "1,000", "2,500", "3,500", "9,999", "", "800", "3,500"],
        ["Stellantis NV (Fiat Chrysler + Groupe PSA)", "2019", "100", "200",
         "300", "999", "", "", ""],                 # matched via OVERRIDE
        ["UNKNOWN CO", "2022", "5", "5", "10", "9", "", "", ""],
        ["", "", ""],                               # blank -> skipped
    ]
    out, missing = cdu_emission_rows(rows, name2lei)

    assert ("ACME", "LEI_ACME", 2022, 1, "", 1000.0) in out
    assert ("ACME", "LEI_ACME", 2022, 2, "location_based", 2500.0) in out
    assert ("Stellantis NV (Fiat Chrysler + Groupe PSA)", "LEI_STLA", 2019, 1, "", 100.0) in out
    assert len(out) == 4                            # 2 ACME + 2 Stellantis
    assert missing == ["UNKNOWN CO"]
    # projection (9,999) and history (800) columns must never appear as values
    assert all(v not in (9999.0, 800.0) for *_, v in out)
    print("ok: latest Scope 1/2 only, LEI map + override, projection/history ignored")


if __name__ == "__main__":
    test_norm()
    test_cdu_rows()
    print("PASS")
