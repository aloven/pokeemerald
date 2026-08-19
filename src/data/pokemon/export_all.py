#!/usr/bin/env python3
"""
export_all.py - Export movesets for every final-stage, split-evolution,
                and single-stage Pokemon in the romhack.

Writes two files into an output/ folder next to this script:
  output/all_movesets.json   - machine-readable structured data
  output/all_movesets.txt    - human-readable 2-column tables

Usage: python3 export_all.py
"""

import json
import sys
from pathlib import Path

# Import everything from the moves module sitting in the same directory
sys.path.insert(0, str(Path(__file__).parent))
from moves import (
    load_all_data,
    build_moveset,
    format_moveset_text,
    find_species_key,
    title_case,
)

# Output to modernemerald/output/ (above the pokeemerald repo)
OUTPUT_DIR = Path(__file__).parents[4] / "output"


def get_export_targets(level_up, tutor, tmhm, evo_chains, evo_edges):
    """
    Return the set of species keys that should be exported:
      - Has no further evolutions (final stage), OR
      - Has multiple evolution paths from it (split evolution, e.g. Slowpoke),
        but include the split targets, not Slowpoke itself in that case
      - Is not part of any evolution chain at all (single-stage)

    In practice: include every species that does NOT appear as a parent in
    evo_edges, as long as it has learnset data.
    """
    all_species = (
        set(level_up.keys()) | set(tutor.keys()) | set(tmhm.keys()) | set(evo_chains.keys())
    )

    # Species that ARE parents (i.e. they evolve into something)
    has_further_evo = set(evo_edges.keys())

    targets = set()
    for sp in all_species:
        if sp == "NONE":
            continue
        # Include if it has no further evolutions
        if sp not in has_further_evo:
            targets.add(sp)

    return sorted(targets)


def main():
    print("Loading data...")
    tmhm_map, evo_chains, evo_edges, level_up, tutor, tmhm, egg_moves, abilities, stats, egg_groups, types = load_all_data()

    targets = get_export_targets(level_up, tutor, tmhm, evo_chains, evo_edges)
    print("Found {} Pokemon to export.".format(len(targets)))

    OUTPUT_DIR.mkdir(exist_ok=True)
    json_path = OUTPUT_DIR / "all_movesets.json"
    txt_path  = OUTPUT_DIR / "all_movesets.txt"

    all_data = []
    txt_blocks = []

    for i, species in enumerate(targets, 1):
        print("  [{}/{}] {}".format(i, len(targets), title_case(species)), end="\r", flush=True)
        data = build_moveset(
            species, tmhm_map, evo_chains,
            level_up, tutor, tmhm, egg_moves, abilities, stats, egg_groups, types
        )
        all_data.append(data)
        txt_blocks.append(format_moveset_text(data))

    print()  # newline after progress line

    # --- Write JSON ---
    with open(json_path, "w") as f:
        json.dump(all_data, f, indent=2)
    print("Wrote {}  ({} entries)".format(json_path, len(all_data)))

    # --- Write TXT ---
    with open(txt_path, "w") as f:
        f.write("\n\n".join(txt_blocks))
        f.write("\n")
    print("Wrote {}".format(txt_path))


if __name__ == "__main__":
    main()
