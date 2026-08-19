#!/usr/bin/env python3
"""
export_moves.py - Export all moves in the game with their properties.

Outputs:
  output/all_moves.json  - machine-readable
  output/all_moves.txt   - human-readable table

Usage: python3 export_moves.py
"""

import re
import json
from pathlib import Path

BASE = Path(__file__).parent
BATTLE_MOVES_FILE = BASE.parent / "battle_moves.h"
DESCRIPTIONS_FILE = BASE.parent / "text" / "move_descriptions.h"
OUTPUT_DIR = BASE.parents[3] / "output"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOWERCASE_WORDS = {"of", "the", "a", "an", "and", "or", "in", "on", "at"}

def title_case(s):
    words = s.replace("_", " ").split()
    result = []
    for i, w in enumerate(words):
        if i == 0 or w.lower() not in _LOWERCASE_WORDS:
            result.append(w.capitalize())
        else:
            result.append(w.lower())
    return " ".join(result)


def type_name(raw):
    """TYPE_FIRE -> Fire"""
    return title_case(raw.replace("TYPE_", "", 1))


def category_name(raw):
    """MOVE_CATEGORY_PHYSICAL -> Physical"""
    return title_case(raw.replace("MOVE_CATEGORY_", "", 1))


def move_display_name(raw):
    """MOVE_FIRE_BLAST -> Fire Blast"""
    return title_case(raw.replace("MOVE_", "", 1))


def var_to_move_key(var_name):
    """
    Convert description variable name to a likely MOVE_ key.
    sPoundDescription -> POUND
    sFirePunchDescription -> FIRE_PUNCH
    sConversion2Description -> CONVERSION_2
    sWillOWispDescription -> WILL_O_WISP
    """
    name = var_name
    if name.startswith("s"):
        name = name[1:]
    if name.endswith("Description"):
        name = name[:-len("Description")]

    # Insert underscores at boundaries
    name = re.sub(r'([a-zA-Z])(\d)', r'\1_\2', name)  # letter->digit
    name = re.sub(r'(\d)([a-zA-Z])', r'\1_\2', name)  # digit->letter
    name = re.sub(r'([a-z])([A-Z])', r'\1_\2', name)  # lowerUpper
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)  # ABCDef -> ABC_Def
    return name.upper()

# ---------------------------------------------------------------------------
# Parse battle_moves.h
# ---------------------------------------------------------------------------

def parse_battle_moves(path):
    """
    Returns list of dicts:
    [{"id": "MOVE_POUND", "name": "Pound", "power": 40, "type": "Normal",
      "accuracy": 100, "pp": 35, "category": "Physical"}, ...]
    """
    text = path.read_text()
    moves = []

    for block in re.finditer(
        r'\[(MOVE_\w+)\]\s*=\s*\{(.*?)\}',
        text, re.DOTALL
    ):
        move_id = block.group(1)
        if move_id == "MOVE_NONE":
            continue

        body = block.group(2)

        power = re.search(r'\.power\s*=\s*(\d+)', body)
        mtype = re.search(r'\.type\s*=\s*(TYPE_\w+)', body)
        accuracy = re.search(r'\.accuracy\s*=\s*(\d+)', body)
        pp = re.search(r'\.pp\s*=\s*(\d+)', body)
        cat = re.search(r'\.category\s*=\s*(MOVE_CATEGORY_\w+)', body)

        moves.append({
            "id":       move_id,
            "name":     move_display_name(move_id),
            "power":    int(power.group(1)) if power else 0,
            "type":     type_name(mtype.group(1)) if mtype else "???",
            "accuracy": int(accuracy.group(1)) if accuracy else 0,
            "pp":       int(pp.group(1)) if pp else 0,
            "category": category_name(cat.group(1)) if cat else "???",
        })

    return moves

# ---------------------------------------------------------------------------
# Parse move_descriptions.h
# ---------------------------------------------------------------------------

def parse_descriptions(path):
    """
    Returns a dict: { "POUND": "Pounds the foe with forelegs or tail.", ... }
    Keyed by the move stem (no MOVE_ prefix).
    """
    text = path.read_text()
    descriptions = {}

    # Match: static const u8 sFooDescription[] = _( "line1\n" "line2" ... );
    for m in re.finditer(
        r'static\s+const\s+u8\s+(s\w+Description)\[\]\s*=\s*_\(\s*(.*?)\);',
        text, re.DOTALL
    ):
        var_name = m.group(1)
        raw_text = m.group(2)

        # Extract all quoted strings and join
        parts = re.findall(r'"(.*?)"', raw_text)
        desc = " ".join(parts).replace("\\n", " ").strip()
        # Collapse multiple spaces
        desc = re.sub(r'\s+', ' ', desc)

        key = var_to_move_key(var_name)
        descriptions[key] = desc

    return descriptions

# ---------------------------------------------------------------------------
# Correlate descriptions to moves
# ---------------------------------------------------------------------------

def match_description(move_id, descriptions):
    """Try to find description for a MOVE_XXX id."""
    # Strip MOVE_ prefix
    key = move_id.replace("MOVE_", "", 1)
    if key in descriptions:
        return descriptions[key]
    return ""

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Parsing battle moves...")
    moves = parse_battle_moves(BATTLE_MOVES_FILE)
    print("  Found {} moves.".format(len(moves)))

    print("Parsing descriptions...")
    descriptions = parse_descriptions(DESCRIPTIONS_FILE)
    print("  Found {} descriptions.".format(len(descriptions)))

    # Attach descriptions
    matched = 0
    for move in moves:
        desc = match_description(move["id"], descriptions)
        move["description"] = desc
        if desc:
            matched += 1
    print("  Matched {} descriptions to moves.".format(matched))

    # Sort alphabetically by name
    moves.sort(key=lambda m: m["name"])

    OUTPUT_DIR.mkdir(exist_ok=True)

    # --- Write JSON ---
    json_path = OUTPUT_DIR / "all_moves.json"
    # Remove internal 'id' from JSON output, keep it clean
    json_data = []
    for m in moves:
        json_data.append({
            "name":        m["name"],
            "type":        m["type"],
            "category":    m["category"],
            "power":       m["power"],
            "accuracy":    m["accuracy"],
            "pp":          m["pp"],
            "description": m["description"],
        })
    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)
    print("Wrote {}  ({} moves)".format(json_path, len(json_data)))

    # --- Write TXT ---
    txt_path = OUTPUT_DIR / "all_moves.txt"
    # Table format
    name_w = max(len(m["name"]) for m in moves)
    type_w = max(len(m["type"]) for m in moves)
    cat_w  = max(len(m["category"]) for m in moves)

    header = "  {:<{nw}}  {:<{tw}}  {:<{cw}}  {:>5}  {:>4}  {:>4}  {}".format(
        "MOVE", "TYPE", "SPLIT", "POWER", "ACC", "PP", "DESCRIPTION",
        nw=name_w, tw=type_w, cw=cat_w
    )
    sep = "=" * max(len(header), 100)

    lines = []
    lines.append(sep)
    lines.append("  ALL MOVES ({} total)".format(len(moves)))
    lines.append(sep)
    lines.append("")
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))

    for m in moves:
        pwr = str(m["power"]) if m["power"] > 0 else "—"
        acc = str(m["accuracy"]) if m["accuracy"] > 0 else "—"
        line = "  {:<{nw}}  {:<{tw}}  {:<{cw}}  {:>5}  {:>4}  {:>4}  {}".format(
            m["name"], m["type"], m["category"], pwr, acc, m["pp"],
            m["description"],
            nw=name_w, tw=type_w, cw=cat_w
        )
        lines.append(line)

    with open(txt_path, "w") as f:
        f.write("\n".join(lines))
        f.write("\n")
    print("Wrote {}".format(txt_path))


if __name__ == "__main__":
    main()
