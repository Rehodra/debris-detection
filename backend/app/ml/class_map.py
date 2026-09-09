"""
Class mapping and metadata for MarineScan Debris Detection model.
Model trained on 7 classes: shipwreck, pipe, ghost_net, marine_debris, aircraft, other, fish.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass(frozen=True)
class ClassMetadata:
    class_id: int
    name: str
    display_name: str
    category: str
    risk_level: str
    color_hex: str
    color_rgb: tuple[int, int, int]
    description: str


CLASS_MAP: Dict[int, ClassMetadata] = {
    0: ClassMetadata(
        class_id=0,
        name="shipwreck",
        display_name="Shipwreck",
        category="Maritime Vessel",
        risk_level="High",
        color_hex="#E63946",
        color_rgb=(230, 57, 70),
        description="Submerged vessel hull, superstructure or derelict wreck presenting navigation or environmental hazards.",
    ),
    1: ClassMetadata(
        class_id=1,
        name="pipe",
        display_name="Subsea Pipeline / Pipe",
        category="Industrial Infrastructure",
        risk_level="High",
        color_hex="#F4A261",
        color_rgb=(244, 162, 97),
        description="Subsea pipeline, conduit, or heavy tubular infrastructure posing navigation and anchor drag hazards.",
    ),
    2: ClassMetadata(
        class_id=2,
        name="ghost_net",
        display_name="Entangled / Ghost Net",
        category="Abandoned Fishing Gear",
        risk_level="Critical",
        color_hex="#E76F51",
        color_rgb=(231, 111, 81),
        description="Abandoned, lost, or discarded fishing gear (ALDFG) presenting severe snagging and marine ecological entrapment hazards.",
    ),
    3: ClassMetadata(
        class_id=3,
        name="marine_debris",
        display_name="Marine Debris / Container",
        category="Anthropogenic Debris",
        risk_level="Moderate",
        color_hex="#E9C46A",
        color_rgb=(233, 196, 106),
        description="Miscellaneous anthropogenic marine debris, discarded drums, shipping containers, or seafloor waste.",
    ),
    4: ClassMetadata(
        class_id=4,
        name="aircraft",
        display_name="Aircraft Wreckage",
        category="Aerospace Debris",
        risk_level="Critical",
        color_hex="#D62828",
        color_rgb=(214, 40, 40),
        description="Downed aircraft wreckage, airframe fragments, or aerospace equipment submerged on the seabed.",
    ),
    5: ClassMetadata(
        class_id=5,
        name="other",
        display_name="Unidentified Target",
        category="Unclassified Target",
        risk_level="Moderate",
        color_hex="#457B9D",
        color_rgb=(69, 123, 157),
        description="Miscellaneous seafloor anomaly or unclassified acoustic reflector requiring further hydrographic survey.",
    ),
    6: ClassMetadata(
        class_id=6,
        name="fish",
        display_name="Marine Organism",
        category="Marine Fauna",
        risk_level="Low",
        color_hex="#2A9D8F",
        color_rgb=(42, 157, 143),
        description="Biological marine life (fish school or individual organism), non-hazardous.",
    ),
}

CLASS_NAMES: Dict[int, str] = {k: v.name for k, v in CLASS_MAP.items()}
NAME_TO_ID: Dict[str, int] = {v.name.lower(): k for k, v in CLASS_MAP.items()}

# Domain aliases for natural language & query variations
ALIASES: Dict[str, int] = {
    "wreck": 0,
    "ship": 0,
    "vessel": 0,
    "pipeline": 1,
    "conduit": 1,
    "steel_pipe": 1,
    "net": 2,
    "entangled_net": 2,
    "fishing_net": 2,
    "aldfg": 2,
    "debris": 3,
    "container": 3,
    "waste": 3,
    "airplane": 4,
    "plane": 4,
    "fuselage": 4,
    "anomaly": 5,
    "unknown": 5,
    "fauna": 6,
    "fish_school": 6,
}


def get_class_name(class_id: int) -> str:
    """Return the normalized class name for a given class ID."""
    metadata = CLASS_MAP.get(class_id)
    return metadata.name if metadata else f"unknown_{class_id}"


def get_class_id(name: str) -> Optional[int]:
    """Return the class ID for a given class name or alias."""
    norm = name.lower().strip().replace(" ", "_").replace("-", "_")
    if norm in NAME_TO_ID:
        return NAME_TO_ID[norm]
    return ALIASES.get(norm)


def get_class_metadata(class_id_or_name: int | str) -> Optional[ClassMetadata]:
    """Retrieve full metadata for a class by ID or name."""
    if isinstance(class_id_or_name, int):
        return CLASS_MAP.get(class_id_or_name)
    class_id = get_class_id(str(class_id_or_name))
    return CLASS_MAP.get(class_id) if class_id is not None else None


def get_all_classes() -> list[Dict[str, Any]]:
    """Return list of all registered class specifications."""
    return [
        {
            "class_id": meta.class_id,
            "name": meta.name,
            "display_name": meta.display_name,
            "category": meta.category,
            "risk_level": meta.risk_level,
            "color_hex": meta.color_hex,
            "color_rgb": list(meta.color_rgb),
            "description": meta.description,
        }
        for meta in CLASS_MAP.values()
    ]
