from __future__ import annotations

from typing import Dict


UNIT_REGISTRY: Dict[str, Dict[str, object]] = {
    "Q11570": {
        "unit_qid": "Q11570",
        "unit_label": "kilogram",
        "canonical_unit": "kg",
        "conversion_factor": 1.0,
        "dimension": "mass",
    },
    "Q613726": {
        "unit_qid": "Q613726",
        "unit_label": "10^21 kilogram",
        "canonical_unit": "kg",
        "conversion_factor": 1.0e21,
        "dimension": "mass",
    },
    "Q828224": {
        "unit_qid": "Q828224",
        "unit_label": "kilometre",
        "canonical_unit": "km",
        "conversion_factor": 1.0,
        "dimension": "length",
    },
    "Q174728": {
        "unit_qid": "Q174728",
        "unit_label": "metre",
        "canonical_unit": "km",
        "conversion_factor": 0.001,
        "dimension": "length",
    },
}


def lookup_unit_qid(unit_qid: str) -> Dict[str, object]:
    qid = str(unit_qid or "").strip().upper()
    if not qid:
        return {}
    return dict(UNIT_REGISTRY.get(qid, {}))
