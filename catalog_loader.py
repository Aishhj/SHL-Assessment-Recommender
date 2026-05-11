"""
catalog_loader.py — loads and caches catalog.json at startup.

The catalog is read once from disk and held in memory for fast lookups.
No external DB is needed.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent / "catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> List[Dict[str, Any]]:
    """
    Load and cache the SHL catalog from catalog.json.
    Raises FileNotFoundError if the file is missing.
    """
    if not CATALOG_PATH.exists():
        logger.error("catalog.json not found at %s", CATALOG_PATH)
        raise FileNotFoundError(
            f"catalog.json not found at {CATALOG_PATH}. "
            "Place your catalog.json in the project root."
        )

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Support both a top-level list or a dict with a key wrapping the list
    if isinstance(data, list):
        catalog = data
    elif isinstance(data, dict):
        # Try common wrapper keys
        for key in ("assessments", "items", "catalog", "products", "data"):
            if key in data and isinstance(data[key], list):
                catalog = data[key]
                break
        else:
            # Fallback: first list value found
            catalog = next(
                (v for v in data.values() if isinstance(v, list)), []
            )
    else:
        catalog = []

    logger.info("Catalog loaded: %d assessments", len(catalog))
    return catalog