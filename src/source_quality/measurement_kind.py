from __future__ import annotations

import re
from typing import Any, Dict


MEASUREMENT_KINDS = {
    "mean_radius",
    "equatorial_radius",
    "polar_radius",
    "volumetric_mean_radius",
    "mass",
    "system_mass",
    "satellite_mass",
    "orbit_target",
    "orbital_distance",
    "semi_major_axis",
    "unknown",
}


def infer_measurement_kind(
    *,
    relation: str,
    raw_text: Any = "",
    source_title: Any = "",
    source_field: Any = "",
) -> Dict[str, Any]:
    relation_name = str(relation or "").strip()
    text = " ".join(str(item or "") for item in (raw_text, source_title, source_field))
    compact = re.sub(r"\s+", " ", text).strip().lower()
    evidence = []
    warning = ""

    def matched(kind: str, confidence: float, reason: str) -> Dict[str, Any]:
        evidence.append(reason)
        return {
            "measurement_kind": kind,
            "confidence": confidence,
            "evidence": evidence[:],
            "warning": warning,
        }

    if relation_name == "HAS_RADIUS":
        if "体积平均" in compact or "volumetric mean" in compact or "vol. mean" in compact:
            return matched("volumetric_mean_radius", 0.95, "matched volumetric mean radius marker")
        if "平均半径" in compact or "mean radius" in compact:
            return matched("mean_radius", 0.92, "matched mean radius marker")
        if "赤道半径" in compact or "equatorial radius" in compact:
            return matched("equatorial_radius", 0.92, "matched equatorial radius marker")
        if "极半径" in compact or "polar radius" in compact:
            return matched("polar_radius", 0.92, "matched polar radius marker")
        return matched("unknown", 0.2, "no radius measurement-kind marker")

    if relation_name == "HAS_MASS":
        if "系统质量" in compact or "system mass" in compact:
            return matched("system_mass", 0.9, "matched system mass marker")
        if "卫星" in compact or "satellite" in compact or "moon" in compact:
            return matched("satellite_mass", 0.65, "matched satellite/source-title mass marker")
        return matched("mass", 0.75, "generic mass relation")

    if relation_name == "ORBITS":
        if "distance from sun" in compact or "距太阳" in compact:
            warning = "Distance from Sun is an orbital-distance field, not a direct orbit-target assertion."
            return matched("orbital_distance", 0.95, "matched distance-from-sun marker")
        return matched("orbit_target", 0.75, "generic orbit target relation")

    if "semi-major" in compact or "semimajor" in compact or "半长轴" in compact:
        return matched("semi_major_axis", 0.9, "matched semi-major axis marker")

    return matched("unknown", 0.1, "no measurement-kind rule matched")
