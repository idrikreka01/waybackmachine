import re
from typing import Any

ERA_KEYWORDS: dict[str, list[str]] = {
    "CLASSIC_47_72": [
        "advance design",
        "task force",
        "apache",
        "3100",
        "3200",
        "3600",
        "3800",
        "c10",
        "c20",
        "c30",
        "k10",
        "k20",
        "k30",
        "stepside",
        "fleetside",
        "longbed",
        "shortbed",
        "big window",
        "small window",
        "napco",
        "67-72",
        "1947",
        "1972",
    ],
    "SQUAREBODY_73_87": [
        "squarebody",
        "73-87",
        "1973-1987",
        "k5 blazer",
        "jimmy",
        "c10",
        "k10",
        "k20",
        "k30",
        "c20",
        "c30",
        "c3500",
        "k3500",
        "suburban",
        "14 bolt",
        "np205",
        "sm465",
        "th400",
        "r10",
        "r20",
        "v10",
        "v20",
    ],
    "GMT400_OBS": [
        "gmt400",
        "obs",
        "c1500",
        "k1500",
        "c2500",
        "k2500",
        "c3500",
        "k3500",
        "88-98",
        "1988-1998",
        "obs tahoe",
        "obs yukon",
    ],
    "GMT800_NBS": [
        "gmt800",
        "nbs",
        "1999-2006",
        "99-06",
        "silverado 1500",
        "silverado 2500",
        "silverado 2500hd",
        "silverado 3500",
        "suburban 2002",
        "tahoe 2000",
        "tahoe 2002",
        "yukon 2002",
        "escalade 2003",
        "avalanche 1500",
        "avalanche 2500",
        "cateye",
        "4l60e",
        "4l80e",
        "lq4",
        "6.0 ls",
        "5.3 ls",
        "knock sensor",
        "p0332",
        "intermediate steering",
        "idler pitman",
    ],
    "GMT900_NNBS": [
        "gmt900",
        "nnbs",
        "2007-2013",
        "07-13",
        "silverado 2008",
        "sierra 2009",
        "tahoe 2010",
        "yukon 2010",
        "escalade 2011",
        "autoride",
        "magneride",
        "afm",
        "6.2l",
        "5.3l",
    ],
    "K2XX": [
        "k2xx",
        "2014-2018",
        "14-18",
        "silverado 2014",
        "silverado 2015",
        "sierra 2014",
        "sierra 2015",
        "ltz",
        "high country",
        "denali",
        "sle",
        "slt",
    ],
    "T1XX_EV": [
        "t1xx",
        "2019",
        "2020",
        "2021",
        "2022",
        "2023",
        "2024",
        "19-23 silverado",
        "zr2",
        "trail boss",
        "silverado ev",
        "sierra ev",
        "at4",
        "dssv",
        "10-speed",
        "2.7 turbo",
    ],
    "DIESEL": [
        "6.2l detroit",
        "6.5l detroit",
        "duramax",
        "lb7",
        "lly",
        "lbz",
        "lmm",
        "lml",
        "l5p",
        "efi live",
        "dpf",
        "def",
    ],
}


TECH_KEYWORDS: dict[str, list[str]] = {
    "INTERIOR": [
        "seat",
        "seats",
        "console",
        "dash",
        "dashboard",
        "cluster",
        "gauge cluster",
        "carpet",
        "headliner",
        "door panel",
        "steering wheel",
    ],
    "EXTERIOR": [
        "paint",
        "rust",
        "bodywork",
        "cab corner",
        "rocker panel",
        "bumper",
        "grille",
        "grill",
        "hood",
        "bed swap",
        "frame restoration",
    ],
    "SUSPENSION": [
        "lift kit",
        "leveling kit",
        "lowering kit",
        "drop kit",
        "torsion key",
        "coilover",
        "shocks",
        "springs",
        "control arms",
        "alignment",
    ],
    "TECH_MAINTENANCE": [
        "overheating",
        "coolant leak",
        "oil leak",
        "misfire",
        "no start",
        "brake pads",
        "rotors",
        "ball joint",
        "idler arm",
        "pitman arm",
        "hub bearing",
        "service",
        "maintenance",
        "troubleshooting",
    ],
    "PERFORMANCE": [
        "cam swap",
        "camshaft",
        "headers",
        "exhaust",
        "intake",
        "intake manifold",
        "throttle body",
        "fuel rail",
        "fuel rails",
        "injectors",
        "mpfi",
        "tbi",
        "csfi",
        "spider injection",
        "vortec",
        "tuning",
        "tune",
        "dyno",
        "horsepower",
        "torque",
        "afm delete",
        "ls swap",
        "big block",
    ],
    "STEREO_ELECTRICAL": [
        "stereo",
        "radio",
        "head unit",
        "speakers",
        "subwoofer",
        "amp",
        "amplifier",
        "wiring",
        "radio harness",
        "stereo harness",
        "electrical issue",
        "short circuit",
        "gauge cluster repair",
        "hvac controls",
    ],
    "DIESEL": [
        "6.2l",
        "6.5l",
        "duramax",
        "diesel injector",
        "turbo",
        "cp3",
        "cp4",
        "glow plug",
        "lift pump",
        "efi live",
        "spade",
        "tuner",
        "dpf",
        "def",
    ],
    "TRANSMISSION": [
        "4l60e",
        "4l80e",
        "th350",
        "th400",
        "sm465",
        "sm420",
        "allison",
        "torque converter",
        "transmission rebuild",
        "slipping",
        "shift kit",
    ],
}


ROUTING_ROWS: list[dict[str, str]] = [
    {
        "era_id": "GMT400_OBS",
        "tech_type": "INTERIOR",
        "forum_main": "GMT400 (1988–1998) – OBS Discussions",
        "forum_sub": "Interior",
    },
    {
        "era_id": "GMT400_OBS",
        "tech_type": "EXTERIOR",
        "forum_main": "GMT400 (1988–1998) – OBS Discussions",
        "forum_sub": "Exterior",
    },
    {
        "era_id": "GMT400_OBS",
        "tech_type": "SUSPENSION",
        "forum_main": "GMT400 (1988–1998) – OBS Discussions",
        "forum_sub": "Suspension: Lifted and Lowered",
    },
    {
        "era_id": "GMT400_OBS",
        "tech_type": "TECH_MAINTENANCE",
        "forum_main": "GMT400 (1988–1998) – OBS Discussions",
        "forum_sub": "Technical & Maintenance",
    },
    {
        "era_id": "GMT400_OBS",
        "tech_type": "PERFORMANCE",
        "forum_main": "GMT400 (1988–1998) – OBS Discussions",
        "forum_sub": "Performance, Mods & Tuning",
    },
    {
        "era_id": "GMT400_OBS",
        "tech_type": "STEREO_ELECTRICAL",
        "forum_main": "GMT400 (1988–1998) – OBS Discussions",
        "forum_sub": "Stereo, Wiring & Electronics",
    },
    {
        "era_id": "K2XX",
        "tech_type": "INTERIOR",
        "forum_main": "K2XX (2014–2018) Discussions",
        "forum_sub": "Interior",
    },
    {
        "era_id": "K2XX",
        "tech_type": "EXTERIOR",
        "forum_main": "K2XX (2014–2018) Discussions",
        "forum_sub": "Exterior",
    },
    {
        "era_id": "K2XX",
        "tech_type": "SUSPENSION",
        "forum_main": "K2XX (2014–2018) Discussions",
        "forum_sub": "Suspension: Lifted and Lowered",
    },
    {
        "era_id": "K2XX",
        "tech_type": "TECH_MAINTENANCE",
        "forum_main": "K2XX (2014–2018) Discussions",
        "forum_sub": "Technical & Maintenance",
    },
    {
        "era_id": "K2XX",
        "tech_type": "PERFORMANCE",
        "forum_main": "K2XX (2014–2018) Discussions",
        "forum_sub": "Performance, Mods & Tuning",
    },
    {
        "era_id": "K2XX",
        "tech_type": "STEREO_ELECTRICAL",
        "forum_main": "K2XX (2014–2018) Discussions",
        "forum_sub": "Stereo, Wiring & Electronics",
    },
    {
        "era_id": "CLASSIC_47_72",
        "tech_type": "INTERIOR",
        "forum_main": "Classic Chevy Trucks (1947–1972)",
        "forum_sub": "Interior",
    },
    {
        "era_id": "CLASSIC_47_72",
        "tech_type": "EXTERIOR",
        "forum_main": "Classic Chevy Trucks (1947–1972)",
        "forum_sub": "Exterior",
    },
    {
        "era_id": "CLASSIC_47_72",
        "tech_type": "SUSPENSION",
        "forum_main": "Classic Chevy Trucks (1947–1972)",
        "forum_sub": "Suspension: Lifted and Lowered",
    },
    {
        "era_id": "CLASSIC_47_72",
        "tech_type": "TECH_MAINTENANCE",
        "forum_main": "Classic Chevy Trucks (1947–1972)",
        "forum_sub": "Technical & Maintenance",
    },
    {
        "era_id": "CLASSIC_47_72",
        "tech_type": "PERFORMANCE",
        "forum_main": "Classic Chevy Trucks (1947–1972)",
        "forum_sub": "Performance, Mods & Tuning",
    },
    {
        "era_id": "CLASSIC_47_72",
        "tech_type": "STEREO_ELECTRICAL",
        "forum_main": "Classic Chevy Trucks (1947–1972)",
        "forum_sub": "Stereo, Wiring & Electronics",
    },
    {
        "era_id": "SQUAREBODY_73_87",
        "tech_type": "INTERIOR",
        "forum_main": "Squarebody Era (1973–1987) Discussions",
        "forum_sub": "Interior",
    },
    {
        "era_id": "SQUAREBODY_73_87",
        "tech_type": "EXTERIOR",
        "forum_main": "Squarebody Era (1973–1987) Discussions",
        "forum_sub": "Exterior",
    },
    {
        "era_id": "SQUAREBODY_73_87",
        "tech_type": "SUSPENSION",
        "forum_main": "Squarebody Era (1973–1987) Discussions",
        "forum_sub": "Suspension: Lifted and Lowered",
    },
    {
        "era_id": "SQUAREBODY_73_87",
        "tech_type": "TECH_MAINTENANCE",
        "forum_main": "Squarebody Era (1973–1987) Discussions",
        "forum_sub": "Technical & Maintenance",
    },
    {
        "era_id": "SQUAREBODY_73_87",
        "tech_type": "PERFORMANCE",
        "forum_main": "Squarebody Era (1973–1987) Discussions",
        "forum_sub": "Performance, Mods & Tuning",
    },
    {
        "era_id": "SQUAREBODY_73_87",
        "tech_type": "STEREO_ELECTRICAL",
        "forum_main": "Squarebody Era (1973–1987) Discussions",
        "forum_sub": "Stereo, Wiring & Electronics",
    },
    {
        "era_id": "GMT800_NBS",
        "tech_type": "INTERIOR",
        "forum_main": "GMT800 (1999–2006) – NBS Discussions",
        "forum_sub": "Interior",
    },
    {
        "era_id": "GMT800_NBS",
        "tech_type": "EXTERIOR",
        "forum_main": "GMT800 (1999–2006) – NBS Discussions",
        "forum_sub": "Exterior",
    },
    {
        "era_id": "GMT800_NBS",
        "tech_type": "SUSPENSION",
        "forum_main": "GMT800 (1999–2006) – NBS Discussions",
        "forum_sub": "Suspension: Lifted and Lowered",
    },
    {
        "era_id": "GMT800_NBS",
        "tech_type": "TECH_MAINTENANCE",
        "forum_main": "GMT800 (1999–2006) – NBS Discussions",
        "forum_sub": "Technical & Maintenance",
    },
    {
        "era_id": "GMT800_NBS",
        "tech_type": "PERFORMANCE",
        "forum_main": "GMT800 (1999–2006) – NBS Discussions",
        "forum_sub": "Performance, Mods & Tuning",
    },
    {
        "era_id": "GMT800_NBS",
        "tech_type": "STEREO_ELECTRICAL",
        "forum_main": "GMT800 (1999–2006) – NBS Discussions",
        "forum_sub": "Stereo, Wiring & Electronics",
    },
    {
        "era_id": "GMT900_NNBS",
        "tech_type": "INTERIOR",
        "forum_main": "GMT900 (2007–2013) – NNBS Discussions",
        "forum_sub": "Interior",
    },
    {
        "era_id": "GMT900_NNBS",
        "tech_type": "EXTERIOR",
        "forum_main": "GMT900 (2007–2013) – NNBS Discussions",
        "forum_sub": "Exterior",
    },
    {
        "era_id": "GMT900_NNBS",
        "tech_type": "SUSPENSION",
        "forum_main": "GMT900 (2007–2013) – NNBS Discussions",
        "forum_sub": "Suspension: Lifted and Lowered",
    },
    {
        "era_id": "GMT900_NNBS",
        "tech_type": "TECH_MAINTENANCE",
        "forum_main": "GMT900 (2007–2013) – NNBS Discussions",
        "forum_sub": "Technical & Maintenance",
    },
    {
        "era_id": "GMT900_NNBS",
        "tech_type": "PERFORMANCE",
        "forum_main": "GMT900 (2007–2013) – NNBS Discussions",
        "forum_sub": "Performance, Mods & Tuning",
    },
    {
        "era_id": "GMT900_NNBS",
        "tech_type": "STEREO_ELECTRICAL",
        "forum_main": "GMT900 (2007–2013) – NNBS Discussions",
        "forum_sub": "Stereo, Wiring & Electronics",
    },
    {
        "era_id": "T1XX_EV",
        "tech_type": "INTERIOR",
        "forum_main": "T1XX (2019 & Beyond) + EVs",
        "forum_sub": "Interior",
    },
    {
        "era_id": "T1XX_EV",
        "tech_type": "EXTERIOR",
        "forum_main": "T1XX (2019 & Beyond) + EVs",
        "forum_sub": "Exterior",
    },
    {
        "era_id": "T1XX_EV",
        "tech_type": "SUSPENSION",
        "forum_main": "T1XX (2019 & Beyond) + EVs",
        "forum_sub": "Suspension: Lifted and Lowered",
    },
    {
        "era_id": "T1XX_EV",
        "tech_type": "TECH_MAINTENANCE",
        "forum_main": "T1XX (2019 & Beyond) + EVs",
        "forum_sub": "Technical & Maintenance",
    },
    {
        "era_id": "T1XX_EV",
        "tech_type": "PERFORMANCE",
        "forum_main": "T1XX (2019 & Beyond) + EVs",
        "forum_sub": "Performance, Mods & Tuning",
    },
    {
        "era_id": "T1XX_EV",
        "tech_type": "STEREO_ELECTRICAL",
        "forum_main": "T1XX (2019 & Beyond) + EVs",
        "forum_sub": "Stereo, Wiring & Electronics",
    },
    {
        "era_id": "DIESEL",
        "tech_type": "DIESEL",
        "forum_main": "Diesel Tech & Duramax Forum",
        "forum_sub": "Diesel Tuning & Emissions",
    },
    # General cross-platform technical forums (catch-all when era is missing or unsupported).
    {
        "era_id": "GENERAL",
        "tech_type": "INTERIOR",
        "forum_main": "General Truck Discussion",
        "forum_sub": "Interior & Cabin",
    },
    {
        "era_id": "GENERAL",
        "tech_type": "EXTERIOR",
        "forum_main": "General Truck Discussion",
        "forum_sub": "Exterior & Body",
    },
    {
        "era_id": "GENERAL",
        "tech_type": "SUSPENSION",
        "forum_main": "General Truck Discussion",
        "forum_sub": "Suspension, Wheels & Tires",
    },
    {
        "era_id": "GENERAL",
        "tech_type": "TECH_MAINTENANCE",
        "forum_main": "General Truck Discussion",
        "forum_sub": "Technical & Maintenance",
    },
    {
        "era_id": "GENERAL",
        "tech_type": "PERFORMANCE",
        "forum_main": "General Truck Discussion",
        "forum_sub": "Performance, Mods & Tuning",
    },
    {
        "era_id": "GENERAL",
        "tech_type": "STEREO_ELECTRICAL",
        "forum_main": "General Truck Discussion",
        "forum_sub": "Audio, Video & Lighting",
    },
    {
        "era_id": "GENERAL",
        "tech_type": "TRANSMISSION",
        "forum_main": "General Truck Discussion",
        "forum_sub": "Transmissions & Drivetrain",
    },
]


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def _score_keywords(text: str, keywords: list[str]) -> int:
    score = 0
    for kw in keywords:
        if not kw:
            continue
        if kw.lower() in text:
            score += 1
    return score


def detect_era(text: str) -> tuple[str, int] | None:
    norm = _normalize(text)
    best_id: str | None = None
    best_score = 0
    for era_id, keywords in ERA_KEYWORDS.items():
        score = _score_keywords(norm, keywords)
        if score > best_score:
            best_score = score
            best_id = era_id
    if best_id is None or best_score == 0:
        return None
    return best_id, best_score


def detect_tech_type(text: str) -> tuple[str, int] | None:
    norm = _normalize(text)
    best_type: str | None = None
    best_score = 0
    for tech_type, keywords in TECH_KEYWORDS.items():
        score = _score_keywords(norm, keywords)
        if score > best_score:
            best_score = score
            best_type = tech_type
    if best_type is None or best_score == 0:
        return None
    return best_type, best_score


def _pick_routing_row(era_id: str, tech_type: str) -> dict[str, str] | None:
    for row in ROUTING_ROWS:
        if row["era_id"] == era_id and row["tech_type"] == tech_type:
            return row
    return None


def _html_to_plain_for_routing(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\\s+", " ", text)
    return text.strip()


def route_thread(thread_payload: dict[str, Any]) -> dict[str, Any]:
    title = thread_payload.get("title") or ""
    first_html = thread_payload.get("first_post_html") or ""
    _ = (thread_payload.get("category_path") or "").lower()
    first_plain = _html_to_plain_for_routing(first_html)
    base_text = f"{title} {first_plain}"
    era = detect_era(base_text)
    tech = detect_tech_type(base_text)

    routing: dict[str, Any] = {
        "era_id": era[0] if era else None,
        "era_score": era[1] if era else 0,
        "tech_type": tech[0] if tech else None,
        "tech_score": tech[1] if tech else 0,
        "forum_main": None,
        "forum_sub": None,
    }
    if tech:
        # First try era-specific routing when we have an era match.
        if era:
            row = _pick_routing_row(era[0], tech[0])
            if row is not None:
                routing["forum_main"] = row["forum_main"]
                routing["forum_sub"] = row["forum_sub"]
        # If no era-specific mapping exists or era is unknown, fall back to GENERAL
        # cross-platform technical forums so that technical threads still have a home.
        if routing["forum_main"] is None or routing["forum_sub"] is None:
            general_row = _pick_routing_row("GENERAL", tech[0])
            if general_row is not None:
                routing["forum_main"] = general_row["forum_main"]
                routing["forum_sub"] = general_row["forum_sub"]

    # Global fallback: if nothing matched, send to General Truck Discussion
    if routing["forum_main"] is None:
        routing["forum_main"] = "General Truck Discussion"
        routing["forum_sub"] = None

    if routing["forum_main"] == "General Truck Discussion":
        routing["era_id"] = "General Truck Discussion"

    return routing
