#!/usr/bin/env python3
"""
moves.py - List all moves a Pokemon can learn in this romhack.

Usage: python3 moves.py <pokemon_name>
Example: python3 moves.py charizard

This file also exposes load_all_data() and build_moveset() for use by
export_all.py.
"""

import sys
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (relative to this script's location)
# ---------------------------------------------------------------------------
BASE = Path(__file__).parent
LEVEL_UP_FILE  = BASE / "level_up_learnsets.h"
TUTOR_FILE     = BASE / "tutor_learnsets.h"
TMHM_FILE      = BASE / "tmhm_learnsets.h"
EGG_FILE       = BASE / "egg_moves.h"
EVOLUTION_FILE = BASE / "evolution.h"
SPECIES_FILE   = BASE / "species_info.h"
TMSHS_FILE     = BASE.parents[2] / "include" / "constants" / "tms_hms.h"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOWERCASE_WORDS = {"of", "the", "a", "an", "and", "or", "in", "on", "at"}

def title_case(s):
    """Convert FIRE_BLAST or FIRE BLAST -> 'Fire Blast'"""
    words = s.replace("_", " ").split()
    result = []
    for i, w in enumerate(words):
        if i == 0 or w.lower() not in _LOWERCASE_WORDS:
            result.append(w.capitalize())
        else:
            result.append(w.lower())
    return " ".join(result)

def move_name(raw):
    """Convert MOVE_FIRE_BLAST -> 'Fire Blast'"""
    return title_case(raw.replace("MOVE_", "", 1))

def ability_name(raw):
    """Convert ABILITY_BLAZE -> 'Blaze'"""
    return title_case(raw.replace("ABILITY_", "", 1))

def normalize(name):
    """Lowercase, strip spaces/underscores/hyphens for fuzzy matching."""
    return name.lower().replace(" ", "").replace("_", "").replace("-", "")

# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def build_tmhm_map(path):
    """{ "FIRE_BLAST": "TM38", "FLY": "HM02", ... }"""
    tm_list, hm_list = [], []
    text = path.read_text()

    tm_block = re.search(r'#define FOREACH_TM\(F\)(.*?)(?=#define|\Z)', text, re.DOTALL)
    if tm_block:
        tm_list = re.findall(r'F\((\w+)\)', tm_block.group(1))

    hm_block = re.search(r'#define FOREACH_HM\(F\)(.*?)(?=#define|\Z)', text, re.DOTALL)
    if hm_block:
        hm_list = re.findall(r'F\((\w+)\)', hm_block.group(1))

    result = {}
    for i, name in enumerate(tm_list, 1):
        result[name] = "TM{:02d}".format(i)
    for i, name in enumerate(hm_list, 1):
        result[name] = "HM{:02d}".format(i)
    return result


def build_evo_chains(path):
    """
    Returns two things as a tuple:
      chains : { species -> [oldest_ancestor, ..., species] }
      edges  : { parent  -> [child, child, ...] }   (for final-stage detection)
    """
    text = path.read_text()
    edges = {}

    for m in re.finditer(
        r'\[SPECIES_(\w+)\]\s*=\s*\{(.*?)\}[,;]',
        text, re.DOTALL
    ):
        parent = m.group(1)
        targets = re.findall(r'SPECIES_(\w+)', m.group(2))
        targets = [t for t in targets if t != "NONE" and t != parent]
        if targets:
            edges[parent] = targets

    child_to_parent = {}
    for parent, children in edges.items():
        for child in children:
            child_to_parent[child] = parent

    def get_chain(species):
        chain = [species]
        current = species
        while current in child_to_parent:
            current = child_to_parent[current]
            chain.append(current)
        chain.reverse()
        return chain

    all_species = set(edges.keys()) | set(child_to_parent.keys())
    chains = {sp: get_chain(sp) for sp in all_species}
    return chains, edges


def parse_stats(path):
    """
    { "CHARIZARD": {"hp": 78, "atk": 84, "def": 78, "spa": 109, "spd": 85, "spe": 100} }
    """
    text = path.read_text()
    result = {}

    species_positions = [(m.group(1), m.start()) for m in
                         re.finditer(r'\[SPECIES_(\w+)\]', text)]

    for i, (species, start) in enumerate(species_positions):
        end = species_positions[i + 1][1] if i + 1 < len(species_positions) else len(text)
        block = text[start:end]

        hp  = re.search(r'\.baseHP\s*=\s*(\d+)', block)
        atk = re.search(r'\.baseAttack\s*=\s*(\d+)', block)
        dfn = re.search(r'\.baseDefense\s*=\s*(\d+)', block)
        spa = re.search(r'\.baseSpAttack\s*=\s*(\d+)', block)
        spd = re.search(r'\.baseSpDefense\s*=\s*(\d+)', block)
        spe = re.search(r'\.baseSpeed\s*=\s*(\d+)', block)

        if hp and atk and dfn and spa and spd and spe:
            result[species] = {
                "hp":  int(hp.group(1)),
                "atk": int(atk.group(1)),
                "def": int(dfn.group(1)),
                "spa": int(spa.group(1)),
                "spd": int(spd.group(1)),
                "spe": int(spe.group(1)),
            }

    return result


def egg_group_name(raw):
    """Convert EGG_GROUP_WATER_1 -> 'Water 1'"""
    return title_case(raw.replace("EGG_GROUP_", "", 1))


def type_display_name(raw):
    """Convert TYPE_FIRE -> 'Fire'"""
    return title_case(raw.replace("TYPE_", "", 1))


def parse_types(path):
    """{ "CHARIZARD": ["Fire", "Flying"] }  (de-duped for mono-type)"""
    text = path.read_text()
    result = {}

    species_positions = [(m.group(1), m.start()) for m in
                         re.finditer(r'\[SPECIES_(\w+)\]', text)]

    for i, (species, start) in enumerate(species_positions):
        end = species_positions[i + 1][1] if i + 1 < len(species_positions) else len(text)
        block = text[start:end]
        # Match .types = { TYPE_X, TYPE_Y } but NOT .types_old
        match = re.search(r'\.types\s*=\s*\{([^}]+)\}', block)
        if match:
            raw_types = re.findall(r'TYPE_\w+', match.group(1))
            types = []
            for t in raw_types:
                name = type_display_name(t)
                if name not in types:
                    types.append(name)
            if types:
                result[species] = types

    return result


def parse_egg_groups(path):
    """{ "CHARIZARD": ["Monster", "Dragon"] }"""
    text = path.read_text()
    result = {}

    species_positions = [(m.group(1), m.start()) for m in
                         re.finditer(r'\[SPECIES_(\w+)\]', text)]

    for i, (species, start) in enumerate(species_positions):
        end = species_positions[i + 1][1] if i + 1 < len(species_positions) else len(text)
        block = text[start:end]
        match = re.search(r'\.eggGroups\s*=\s*\{([^}]+)\}', block)
        if match:
            raw_groups = re.findall(r'EGG_GROUP_\w+', match.group(1))
            # De-duplicate (many Pokemon list the same group twice)
            seen = []
            for g in raw_groups:
                name = egg_group_name(g)
                if name not in seen and name != "No Eggs Discovered":
                    seen.append(name)
            if seen:
                result[species] = seen

    return result


def parse_abilities(path):
    """{ "CHARIZARD": ["Blaze", "Solar Power"] }"""
    text = path.read_text()
    result = {}

    species_positions = [(m.group(1), m.start()) for m in
                         re.finditer(r'\[SPECIES_(\w+)\]', text)]

    for i, (species, start) in enumerate(species_positions):
        end = species_positions[i + 1][1] if i + 1 < len(species_positions) else len(text)
        block = text[start:end]
        abilities_match = re.search(r'\.abilities\s*=\s*\{([^}]+)\}', block)
        if abilities_match:
            raw_abilities = re.findall(r'ABILITY_\w+', abilities_match.group(1))
            filtered = [ability_name(a) for a in raw_abilities if a != "ABILITY_NONE"]
            if filtered:
                result[species] = filtered

    return result


def parse_level_up(path):
    """{ "CHARIZARD": [("MOVE_FIRE_BLAST", 34), ...] }"""
    text = path.read_text()
    result = {}

    for block in re.finditer(
        r's(\w+)LevelUpLearnset\[\]\s*=\s*\{(.*?)\};',
        text, re.DOTALL
    ):
        species = block.group(1).upper()
        moves = re.findall(r'LEVEL_UP_MOVE\(\s*(\d+)\s*,\s*(MOVE_\w+)\s*\)', block.group(2))
        result[species] = [(mv, int(lvl)) for lvl, mv in moves]

    return result


def parse_tutor(path):
    """{ "CHARIZARD": ["MOVE_FIRE_PUNCH", ...] }"""
    text = path.read_text()
    result = {}

    tutor_index = {}
    for m in re.finditer(r'\[TUTOR_(\w+)\]\s*=\s*(MOVE_\w+)', text):
        tutor_index["TUTOR_{}".format(m.group(1))] = m.group(2)

    for block in re.finditer(
        r's(\w+)TutorLearnset\[\]\s*=\s*\{(.*?)\};',
        text, re.DOTALL
    ):
        species = block.group(1).upper()
        raw_entries = re.findall(r'TUTOR\((MOVE_\w+)\)', block.group(2))
        moves = []
        for entry in raw_entries:
            key = "TUTOR_{}".format(entry)
            moves.append(tutor_index.get(key, entry))
        result[species] = moves

    return result


def parse_tmhm(path):
    """{ "CHARIZARD": ["FIRE_BLAST", "FLY", ...] }"""
    text = path.read_text()
    result = {}

    for block in re.finditer(
        r'\[SPECIES_(\w+)\]\s*=\s*\{[^}]*\.learnset\s*=\s*\{(.*?)\}\s*\}',
        text, re.DOTALL
    ):
        species = block.group(1)
        moves = re.findall(r'\.(\w+)\s*=\s*TRUE', block.group(2))
        result[species] = moves

    return result


def parse_egg_moves(path):
    """{ "CHARMANDER": ["MOVE_BELLY_DRUM", ...] }"""
    text = path.read_text()
    result = {}

    for block in re.finditer(
        r'egg_moves\((\w+),(.*?)(?=egg_moves\(|\Z)',
        text, re.DOTALL
    ):
        species = block.group(1)
        moves = re.findall(r'(MOVE_\w+)', block.group(2))
        result[species] = moves

    return result


def find_species_key(name, all_keys):
    """Case/punctuation-insensitive lookup into a set of species keys."""
    target = normalize(name)
    for key in all_keys:
        if normalize(key) == target:
            return key
    return None

# ---------------------------------------------------------------------------
# Load all data in one call (shared by moves.py and export_all.py)
# ---------------------------------------------------------------------------

def load_all_data():
    """Parse every source file and return all data dicts."""
    tmhm_map            = build_tmhm_map(TMSHS_FILE)
    evo_chains, evo_edges = build_evo_chains(EVOLUTION_FILE)
    level_up            = parse_level_up(LEVEL_UP_FILE)
    tutor               = parse_tutor(TUTOR_FILE)
    tmhm                = parse_tmhm(TMHM_FILE)
    egg_moves           = parse_egg_moves(EGG_FILE)
    abilities           = parse_abilities(SPECIES_FILE)
    stats               = parse_stats(SPECIES_FILE)
    egg_groups          = parse_egg_groups(SPECIES_FILE)
    types               = parse_types(SPECIES_FILE)
    return tmhm_map, evo_chains, evo_edges, level_up, tutor, tmhm, egg_moves, abilities, stats, egg_groups, types

# ---------------------------------------------------------------------------
# Core moveset builder — returns structured data, no printing
# ---------------------------------------------------------------------------

PRIO_LEVEL  = 0
PRIO_TMHM   = 1
PRIO_TUTOR  = 2
PRIO_EGG    = 3
PRIO_PREVO  = 4

PRIO_LABEL = {
    PRIO_LEVEL:  "LEVEL",
    PRIO_TMHM:   "TMHM",
    PRIO_TUTOR:  "TUTOR",
    PRIO_EGG:    "EGG",
    PRIO_PREVO:  "PRIOR_EVOLUTION",
}


def build_moveset(species, tmhm_map, evo_chains, level_up, tutor, tmhm, egg_moves, abilities, stats, egg_groups, types):
    """
    Returns a dict:
    {
        "species":    "CHARIZARD",
        "abilities":  ["Blaze"],
        "egg_groups": ["Monster", "Dragon"],
        "stats":      {"hp": 78, "atk": 84, "def": 78, "spa": 109, "spd": 85, "spe": 100},
        "bst":        534,
        "moves": [
            {"name": "Fire Blast", "sources": [{"type": "LEVEL", "level": 34}]},
            {"name": "Fly",        "sources": [{"type": "TMHM",  "number": "HM02"}]},
            ...
        ]
    }
    Moves that can be learned via multiple methods carry multiple sources.
    """
    chain = evo_chains.get(species, [species])
    if species in chain:
        idx = chain.index(species)
        ancestors = chain[:idx]
    else:
        ancestors = []
    base_species = chain[0] if chain else species

    # seen: move_key -> list of source dicts (we keep ALL sources, unlike the
    # display path which only shows the highest-priority one)
    seen = {}   # move_key -> [source_dict, ...]
    seen_prio = {}  # move_key -> lowest prio seen (for prior-evo dedup only)

    def add_source(move_key, source, prio):
        if move_key not in seen:
            seen[move_key] = []
            seen_prio[move_key] = prio
        seen[move_key].append(source)
        if prio < seen_prio[move_key]:
            seen_prio[move_key] = prio

    # 1. Level-up moves (this species)
    # Many Pokemon list moves at level 1 as "reminder" entries AND at their
    # real learn level. We want to show both: "Level 1+62" means relearnable
    # early via Move Relearner but naturally learned at 62.
    level_up_levels = {}  # mv -> set of levels
    for mv, lvl in level_up.get(species, []):
        if mv not in level_up_levels:
            level_up_levels[mv] = set()
        level_up_levels[mv].add(lvl)
    for mv, levels in level_up_levels.items():
        sorted_levels = sorted(levels)
        if len(sorted_levels) > 1 and sorted_levels[0] == 1:
            # Has a reminder at 1 plus a real learn level
            level_str = "+".join(str(l) for l in sorted_levels)
        else:
            # Just use the highest level
            level_str = str(max(sorted_levels))
        add_source(mv, {"type": "LEVEL", "level": max(sorted_levels), "level_display": level_str}, PRIO_LEVEL)

    # 2. TM/HM
    for tmhm_key in tmhm.get(species, []):
        number = tmhm_map.get(tmhm_key, "TM??")
        mv = "MOVE_{}".format(tmhm_key)
        add_source(mv, {"type": "TMHM", "number": number}, PRIO_TMHM)

    # 3. Tutor
    for mv in tutor.get(species, []):
        add_source(mv, {"type": "TUTOR"}, PRIO_TUTOR)

    # 4. Egg moves
    egg_key = find_species_key(base_species, set(egg_moves.keys()))
    if egg_key:
        for mv in egg_moves[egg_key]:
            add_source(mv, {"type": "EGG"}, PRIO_EGG)

    # 5. Prior evolution level-up (only if move not already in set)
    for ancestor in ancestors:
        anc_display = title_case(ancestor)
        for mv, lvl in level_up.get(ancestor, []):
            if mv not in seen:
                add_source(mv, {"type": "PRIOR_EVOLUTION", "pokemon": anc_display}, PRIO_PREVO)

    # Sort same as display: level-up by level, rest alphabetically within group
    def sort_key(item):
        mv_key, sources = item
        prio = seen_prio[mv_key]
        if prio == PRIO_LEVEL:
            lvl_num = min(s["level"] for s in sources if s["type"] == "LEVEL")
            return (prio, lvl_num, move_name(mv_key))
        return (prio, 0, move_name(mv_key))

    sorted_moves = sorted(seen.items(), key=sort_key)

    moves_list = []
    for mv_key, sources in sorted_moves:
        moves_list.append({
            "name": move_name(mv_key),
            "sources": sources,
        })

    sp_stats = stats.get(species, {})
    bst = sum(sp_stats.values()) if sp_stats else 0

    return {
        "species":    species,
        "types":      types.get(species, []),
        "abilities":  abilities.get(species, []),
        "egg_groups": egg_groups.get(species, []),
        "stats":      sp_stats,
        "bst":        bst,
        "moves":      moves_list,
    }

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def source_label(source):
    """Turn a source dict into a human-readable label string."""
    t = source["type"]
    if t == "LEVEL":
        display = source.get("level_display", str(source["level"]))
        return "Level Up, Level {}".format(display)
    if t == "TMHM":
        return source["number"]
    if t == "TUTOR":
        return "Move Tutor"
    if t == "EGG":
        return "Egg Move"
    if t == "PRIOR_EVOLUTION":
        return "Prior Evolution, {}".format(source["pokemon"])
    return t


def format_moveset_text(data):
    """
    Render a moveset dict as the human-readable 2-column terminal output.
    Returns a string (no trailing newline).
    """
    species_abilities = data["abilities"]
    ability_str = " / ".join(species_abilities) if species_abilities else "Unknown"
    egg_grps = data.get("egg_groups", [])
    egg_str = " / ".join(egg_grps) if egg_grps else "No Eggs"
    sp_types = data.get("types", [])
    type_str = " / ".join(sp_types) if sp_types else "???"
    display = title_case(data["species"])
    header = "{} [{} | {}] ({})".format(display, type_str, ability_str, egg_str)

    # Build stats line
    st = data.get("stats", {})
    bst = data.get("bst", 0)
    if st:
        stats_line = "BST: {} | {} HP, {} Atk, {} Def, {} SpA, {} SpD, {} Spe".format(
            bst, st["hp"], st["atk"], st["def"], st["spa"], st["spd"], st["spe"]
        )
    else:
        stats_line = ""

    # Group moves by their primary source type (lowest prio = first source added)
    # For display we show the single best label per move
    groups = {}   # prio -> list of "Move Name [Label]" strings
    group_order = []

    for move in data["moves"]:
        # Pick the display label: prefer LEVEL > TMHM > TUTOR > EGG > PRIOR_EVO
        best = sorted(move["sources"], key=lambda s: [
            "LEVEL", "TMHM", "TUTOR", "EGG", "PRIOR_EVOLUTION"
        ].index(s["type"]) if s["type"] in ["LEVEL","TMHM","TUTOR","EGG","PRIOR_EVOLUTION"] else 99)
        label = source_label(best[0])
        prio = ["LEVEL","TMHM","TUTOR","EGG","PRIOR_EVOLUTION"].index(best[0]["type"])
        if prio not in groups:
            groups[prio] = []
            group_order.append(prio)
        groups[prio].append("{} [{}]".format(move["name"], label))

    all_entries = [e for p in group_order for e in groups[p]]
    col_width = max((len(e) for e in all_entries), default=40)
    total_width = max(col_width * 2 + 6, len(header) + 4, len(stats_line) + 4 if stats_line else 0)

    lines = []
    lines.append("=" * total_width)
    lines.append("  " + header)
    if stats_line:
        lines.append("  " + stats_line)
    lines.append("=" * total_width)

    for prio in group_order:
        entries = groups[prio]
        lines.append("")
        half = (len(entries) + 1) // 2
        left_col  = entries[:half]
        right_col = entries[half:]
        for i, left in enumerate(left_col):
            right = right_col[i] if i < len(right_col) else ""
            if right:
                lines.append("  {:<{w}}  {}".format(left, right, w=col_width))
            else:
                lines.append("  {}".format(left))

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Main (single-pokemon interactive use)
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 moves.py <pokemon_name>")
        print("Example: python3 moves.py charizard")
        sys.exit(1)

    input_name = sys.argv[1]

    tmhm_map, evo_chains, evo_edges, level_up, tutor, tmhm, egg_moves, abilities, stats, egg_groups, types = load_all_data()

    all_species = (
        set(level_up.keys()) | set(tutor.keys()) |
        set(tmhm.keys()) | set(evo_chains.keys())
    )
    species = find_species_key(input_name, all_species)
    if species is None:
        print("Error: Pokemon '{}' not found.".format(input_name))
        sys.exit(1)

    data = build_moveset(species, tmhm_map, evo_chains, level_up, tutor, tmhm, egg_moves, abilities, stats, egg_groups, types)
    print()
    print(format_moveset_text(data))
    print()


if __name__ == "__main__":
    main()
