"""Hardware identification data tables used by the detector.

These tables were previously inline in ``abso/core/detector.py``. Moving
them here keeps the detector's flow free of multi-screen literal blocks
and gives us a single place to add new entries when new OEM models,
G-Sync displays, or SMBIOS chassis codes appear.

Nothing here is dynamic — all tables are immutable module-level data.
Importers should treat the returned containers as read-only.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# OEM manufacturers (Win32_ComputerSystem.Manufacturer)
# ---------------------------------------------------------------------------

#: Manufacturer strings that strongly indicate a pre-built / OEM system.
#: Matched case-insensitively via substring containment.
OEM_MANUFACTURERS: Final[frozenset[str]] = frozenset({
    "dell", "dell inc.", "dell inc",
    "hp", "hewlett-packard", "hewlett packard",
    "lenovo",
    "acer", "acer inc.",
    "asus", "asustek computer inc.", "asustek",
    "msi", "micro-star international",
    "alienware",
    "razer", "razer inc.",
    "samsung", "samsung electronics",
    "lg", "lg electronics",
    "microsoft", "microsoft corporation",
    "apple", "apple inc.",
    "intel", "intel corporation",
    "nzxt",
    "corsair",
    "ibuypower", "ibuypower inc",
    "cyberpower", "cyberpowerpc",
    "origin pc", "origin",
    "maingear",
    "digital storm",
    "falcon northwest",
})

#: Placeholder strings WMI surfaces when SMBIOS fields are uninitialized.
#: Presence of any of these on Manufacturer / Model / SystemFamily means
#: the system is almost certainly a custom build.
GENERIC_SMBIOS_PLACEHOLDERS: Final[tuple[str, ...]] = (
    "to be filled",
    "default string",
    "system manufacturer",
    "system product name",
    "not applicable",
    "n/a",
    "oem",
    "o.e.m.",
)

#: Substring fragments of motherboard product names that indicate the
#: system Model field is parroting the motherboard model (i.e. custom
#: build, not a pre-built with consumer branding).
MOTHERBOARD_MODEL_PATTERNS: Final[tuple[str, ...]] = (
    "ms-",                                          # MSI codes (MS-7D98)
    "rog ", "rog-", "prime ", "tuf ", "proart ",    # ASUS lines
    "meg ", "mpg ", "mag ", "pro ",                 # MSI lines
    "aorus", "gaming x", "eagle",                   # Gigabyte lines
    "-cf", "-f", "-e", "-a", "-i", "-p",            # Common board suffixes
)


# ---------------------------------------------------------------------------
# Known OEM motherboard → pre-built mapping
# ---------------------------------------------------------------------------

#: Triples of (motherboard_model_substring, oem_manufacturer, friendly_name).
#: The substring is matched case-insensitively against
#: ``Win32_BaseBoard.Product``. ``oem_manufacturer`` may be ``None`` for
#: the catch-all "BULK" generic-OEM signal.
OEM_MOTHERBOARD_LOOKUP: Final[tuple[tuple[str, str | None, str | None], ...]] = (
    # MSI Aegis series
    ("pro b760-vc wifi 7 bulk", "MSI", "MSI Aegis R2 14th"),
    ("pro b760-vc wifi bulk", "MSI", "MSI Aegis R2"),
    ("pro b760m-vc wifi bulk", "MSI", "MSI Aegis R2 (Micro-ATX)"),
    ("pro b660-vc wifi bulk", "MSI", "MSI Aegis R"),
    ("pro z790-vc wifi bulk", "MSI", "MSI Aegis RS 14th"),
    ("pro z690-vc wifi bulk", "MSI", "MSI Aegis RS"),
    # MSI Trident series
    ("pro b760-vc wifi 7 trident", "MSI", "MSI Trident"),
    # MSI Infinite series
    ("pro b760 infinite", "MSI", "MSI Infinite"),
    # Dell (often use internal codenames)
    ("0crh6c", "Dell", "Dell Desktop"),
    ("optiplex", "Dell", "Dell OptiPlex"),
    ("xps", "Dell", "Dell XPS"),
    ("alienware", "Dell", "Alienware"),
    # HP
    ("omen", "HP", "HP OMEN"),
    ("pavilion", "HP", "HP Pavilion"),
    ("envy", "HP", "HP ENVY"),
    # Lenovo
    ("legion", "Lenovo", "Lenovo Legion"),
    ("ideacentre", "Lenovo", "Lenovo IdeaCentre"),
    ("thinkcentre", "Lenovo", "Lenovo ThinkCentre"),
    # ASUS ROG pre-builts
    ("rog strix ga", "ASUS", "ASUS ROG Strix GA"),
    ("rog strix gt", "ASUS", "ASUS ROG Strix GT"),
    # Generic OEM indicator — any "BULK" suffix motherboard
    ("bulk", None, None),
)


# ---------------------------------------------------------------------------
# SMBIOS chassis type codes (Win32_SystemEnclosure.ChassisTypes)
# ---------------------------------------------------------------------------

#: Mapping of SMBIOS chassis type code → human-readable label, per DMTF
#: SMBIOS specification §7.4.1.
SMBIOS_CHASSIS_TYPES: Final[dict[int, str]] = {
    1: "Other",
    2: "Unknown",
    3: "Desktop",
    4: "Low Profile Desktop",
    5: "Pizza Box",
    6: "Mini Tower",
    7: "Tower",
    8: "Portable",
    9: "Laptop",
    10: "Notebook",
    11: "Hand Held",
    12: "Docking Station",
    13: "All in One",
    14: "Sub Notebook",
    15: "Space-saving",
    16: "Lunch Box",
    17: "Main Server Chassis",
    18: "Expansion Chassis",
    19: "SubChassis",
    20: "Bus Expansion Chassis",
    21: "Peripheral Chassis",
    22: "RAID Chassis",
    23: "Rack Mount Chassis",
    24: "Sealed-case PC",
    25: "Multi-system chassis",
    26: "Compact PCI",
    27: "Advanced TCA",
    28: "Blade",
    29: "Blade Enclosure",
    30: "Tablet",
    31: "Convertible",
    32: "Detachable",
    33: "IoT Gateway",
    34: "Embedded PC",
    35: "Mini PC",
    36: "Stick PC",
}


# ---------------------------------------------------------------------------
# Legacy hardcoded G-Sync monitor patterns
# ---------------------------------------------------------------------------

# These tables are a DEPRECATED last-resort fallback. ABSO prefers EDID
# parsing + NVIDIA registry/DRS detection (see ``detect_monitors``). The
# tables are kept here, not inline in detector.py, so the next time we
# need to drop the fallback entirely the touchpoint is a single file.

#: Substrings that identify a panel as G-Sync Ultimate (native hardware module).
GSYNC_ULTIMATE_PATTERNS: Final[tuple[str, ...]] = (
    "PG27UQ", "PG65UQ", "X27", "X35",       # ASUS ROG Swift
    "27GN950", "38GN950",                   # LG UltraGear
    "AW5520QF", "AW2721D",                  # Alienware
)

#: Substrings that identify a panel as G-Sync (native hardware module).
GSYNC_NATIVE_PATTERNS: Final[tuple[str, ...]] = (
    "PG279Q", "PG278Q", "PG248Q", "PG258Q", # ASUS ROG Swift
    "XB271HU", "XB270HU", "XB280HK",        # Acer Predator
    "27GK750F",                             # LG
)
