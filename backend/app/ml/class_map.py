"""
Class mapping and metadata for MarineScan Debris Detection model.
Model trained on 3 classes: ghost_net, pipe, marine_debris.
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
        name="ghost_net",
        display_name="Ghost Fishing Net",
        category="Derelict Fishing Gear",
        risk_level="Critical",
        color_hex="#E63946",
        color_rgb=(230, 57, 70),
        description="Abandoned, lost, or discarded fishing net actively entangling marine life and snagging vessel gear."
    ),
    1: ClassMetadata(
        class_id=1,
        name="pipe",
        display_name="Subsea Pipeline / Cylinder",
        category="Submerged Infrastructure",
        risk_level="High",
        color_hex="#F4A261",
        color_rgb=(244, 162, 97),
        description="Rigid cylindrical infrastructure such as a subsea pipeline segment, conduit, or cable casing."
    ),
    2: ClassMetadata(
        class_id=2,
        name="marine_debris",
        display_name="Marine Debris",
        category="Anthropogenic Debris",
        risk_level="Moderate",
        color_hex="#2A9D8F",
        color_rgb=(42, 157, 143),
        description="Miscellaneous man-made debris such as containers, drums, tires, or other discarded material on the seabed."
    ),
}

CLASS_NAMES: Dict[int, str] = {k: v.name for k, v in CLASS_MAP.items()}
NAME_TO_ID: Dict[str, int] = {v.name.lower(): k for k, v in CLASS_MAP.items()}


def get_class_name(class_id: int) -> str:
    """Return the normalized class name for a given class ID."""
    metadata = CLASS_MAP.get(class_id)
    return metadata.name if metadata else f"unknown_{class_id}"


def get_class_id(name: str) -> Optional[int]:
    """Return the class ID for a given class name."""
    return NAME_TO_ID.get(name.lower().strip())


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
