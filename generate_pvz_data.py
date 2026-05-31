import json
import re
import math

# ============================================================
# CONFIGURATION — tweak these weights to change similarity
# ============================================================
WEIGHTS = {
    "cost":     2.0,
    "strength": 1.0,
    "health":   1.0,
    "class":    3.0,   # Guardian, Solar, Kabloom, etc.
    "type":     3.0,   # Plant, Zombie, Trick, Environment
    "tribes":   4.0,   # Root, Nut, Dancing, etc.
    "keywords": 3.0,   # exact keyword match
    "category": 2.0,   # shared keyword category (trigger, aggro, tempo, control, passive)
}

MAX_COST = 11
MAX_STAT = 20

# ============================================================
# KEYWORD NORMALIZATION
# Left = raw text from <b> tags, Right = canonical name used in vectors
# ============================================================
KEYWORD_MAP = {
    "when played:": "when played", "when played": "when played",
    "when played on heights:": "when played on heights", "when played on heights": "when played on heights",
    "when played on the ground": "when played on the ground",
    "when played behind a plant:": "when played behind a plant",
    "when played next to a zombie:": "when played next to a zombie", "when played next to a zombie": "when played next to a zombie",
    "when played in an environment:": "when played in an environment",
    "when played on heights or an environment:": "when played on heights",
    "when played next to a leafy plant": "when played next to a leafy plant",
    "when revealed:": "when revealed", "when revealed": "when revealed",
    "when revealed in an environment:": "when revealed in an environment",
    "when revealed on heights:": "when revealed on heights",
    "when destroyed:": "when destroyed", "when destroyed": "when destroyed",
    "when hurt:": "when hurt", "when hurt": "when hurt",
    "when this hurts the plant hero": "when this hurts the plant hero",
    "when this enters a lane:": "when this enters a lane",
    "start of turn:": "start of turn", "start of turn": "start of turn",
    "end of turn:": "end of turn", "end of turn": "end of turn",
    "start of tricks:": "start of tricks",
    "before combat here:": "before combat here", "before combat here": "before combat here",
    "after combat here:": "after combat here",
    "while in your hand:": "while in your hand",
    "while in an environment:": "while in an environment", "while in an environment": "while in an environment",
    "dino-roar:": "dino-roar", "dino-roar": "dino-roar",
    "fusion:": "fusion",
    "amphibious": "amphibious", "amphibious.": "amphibious",
    "bullseye": "bullseye", "{{truestrike}}bullseye": "bullseye",
    "team-up": "team-up",
    "gravestone": "gravestone",
    "frenzy": "frenzy", "strikethrough": "strikethrough",
    "freeze": "freeze", "bounce": "bounce", "deadly": "deadly",
    "double strike": "double strike", "untrickable": "untrickable",
    "hunt": "hunt",
    "conjure": "conjure", "conjures": "conjure", "when played: conjure": "conjure",
    "plant evolution": "evolution", "zombie evolution": "evolution",
    "nut evolution": "evolution", "berry evolution:": "evolution",
    "mushroom evolution": "evolution", "leafy evolution": "evolution",
    "pea evolution": "evolution", "bean evolution": "evolution",
    "team-up evolution": "evolution", "mustache evolution": "evolution",
    "dancing evolution": "evolution", "pirate evolution:": "evolution",
    "professional evolution": "evolution", "sports evolution": "evolution",
    "anti-hero 2": "anti-hero", "anti-hero 3": "anti-hero",
    "anti-hero 4": "anti-hero", "anti-hero 5": "anti-hero",
    "armored 1": "armored", "armored 2": "armored",
    "overshoot 2": "overshoot", "overshoot 3": "overshoot",
    "splash damage 1": "splash damage", "splash damage 2": "splash damage",
    "splash damage 3": "splash damage", "splash damage 4": "splash damage",
    "splash damage 6": "splash damage",
    "half": None,
    "bonus attack": "bonus attack",
    "heal ": "heal",
    "heal": "heal",
    "healed": "heal",
    "{{amphibious:a:amphibious is:plant type:f}}": "amphibious",
    "{{team-up:a:team-up type:f}}": "team-up",
    "{{gravestone:a:gravestone type:f is:zombie -\"headstone carver\" - \"grave robber\" -\"mixed-up gravedigger\"}}": "gravestone",
}

# ============================================================
# KEYWORD CATEGORIES
# A keyword can belong to multiple categories.
# Cards sharing a category get partial similarity credit
# even if they don't share the exact same keyword.
# ============================================================
KEYWORD_CATEGORIES = {
    # TRIGGER — fires on a condition
    "when played":                       ["trigger"],
    "when played on heights":            ["trigger"],
    "when played on the ground":         ["trigger"],
    "when played behind a plant":        ["trigger"],
    "when played next to a zombie":      ["trigger"],
    "when played in an environment":     ["trigger"],
    "when played next to a leafy plant": ["trigger"],
    "when revealed":                     ["trigger"],
    "when revealed in an environment":   ["trigger"],
    "when revealed on heights":          ["trigger"],
    "when destroyed":                    ["trigger"],
    "when hurt":                         ["trigger"],
    "when this hurts the plant hero":    ["trigger"],
    "when this enters a lane":           ["trigger"],
    "start of turn":                     ["trigger"],
    "end of turn":                       ["trigger"],
    "start of tricks":                   ["trigger"],
    "before combat here":                ["trigger"],
    "after combat here":                 ["trigger"],
    "while in your hand":                ["trigger"],
    "while in an environment":           ["trigger"],
    "dino-roar":                         ["trigger", "tempo"],

    # PASSIVE — always-on keyword abilities
    "team-up":                           ["passive"],
    "amphibious":                        ["passive"],
    "untrickable":                       ["passive", "control"],
    "gravestone":                        ["passive"],
    "fusion":                            ["passive"],

    # AGGRO — increases damage output or helps attacking
    "bullseye":                          ["aggro"],
    "frenzy":                            ["aggro"],
    "strikethrough":                     ["aggro"],
    "double strike":                     ["aggro"],
    "overshoot":                         ["aggro"],
    "anti-hero":                         ["aggro"],
    "bonus attack":                      ["aggro"],
    "splash damage":                     ["aggro", "tempo"],
    "deadly":                            ["aggro", "control"],

    # TEMPO — generates stat advantages or value
    "armored":                           ["tempo"],
    "conjure":                           ["tempo"],
    "evolution":                         ["tempo"],
    "heal":                              ["tempo"],

    # CONTROL — disrupts or controls the board
    "freeze":                            ["control"],
    "bounce":                            ["control"],
    "hunt":                              ["control"],

    

    
}

ALL_CATEGORIES = ["trigger", "passive", "aggro", "tempo", "control"]

# ============================================================
# HELPERS
# ============================================================
def extract_keywords(abilities):
    if not abilities:
        return set()
    raw = re.findall(r'<b>(.*?)</b>', abilities)
    result = set()
    for kw in raw:
        normalized = kw.strip().lower()
        mapped = KEYWORD_MAP.get(normalized, normalized)
        if mapped:
            result.add(mapped)
    return result

def get_categories(keywords):
    """Given a set of canonical keywords, return a dict of category -> total weight."""
    cats = {c: 0.0 for c in ALL_CATEGORIES}
    for kw in keywords:
        for cat in KEYWORD_CATEGORIES.get(kw, []):
            cats[cat] += 1.0
    return cats

def build_vector(card, all_classes, all_types, all_tribes, all_kw):
    vec = []

    # Numeric stats
    vec.append(WEIGHTS["cost"]     * (card.get('cost') or 0)     / MAX_COST)
    vec.append(WEIGHTS["strength"] * (card.get('strength') or 0) / MAX_STAT)
    vec.append(WEIGHTS["health"]   * (card.get('health') or 0)   / MAX_STAT)

    # Class (one-hot)
    cls = card.get('class', '')
    for c in all_classes:
        vec.append(WEIGHTS["class"] if c == cls else 0.0)

    # Type (one-hot)
    typ = card.get('type', '')
    for t in all_types:
        vec.append(WEIGHTS["type"] if t == typ else 0.0)

    # Tribes (multi-hot, normalized by tribe count)
    tribes = set(card.get('tribes', []))
    n_tribes = max(len(tribes), 1)
    for t in all_tribes:
        vec.append(WEIGHTS["tribes"] / math.sqrt(n_tribes) if t in tribes else 0.0)

    # Exact keywords (multi-hot, normalized by keyword count)
    kws = extract_keywords(card.get('abilities', ''))
    n_kws = max(len(kws), 1)
    for kw in all_kw:
        vec.append(WEIGHTS["keywords"] / math.sqrt(n_kws) if kw in kws else 0.0)

    # Keyword categories (how much of each category this card belongs to)
    cats = get_categories(kws)
    total_cat = max(sum(cats.values()), 1)
    for cat in ALL_CATEGORIES:
        vec.append(WEIGHTS["category"] * cats[cat] / math.sqrt(total_cat))

    return vec

def cosine_sim(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0
    return dot / (mag_a * mag_b)

# ============================================================
# MAIN
# ============================================================
def generate(input_json, output_json):
    print(f"Loading {input_json}...")
    with open(input_json, 'r') as f:
        cards = json.load(f)

    cards = [c for c in cards if c.get('class') != 'Removed']
    print(f"Cards after filtering: {len(cards)}")

    all_classes = sorted(set(c.get('class', '') for c in cards))
    all_types   = sorted(set(c.get('type', '') for c in cards))
    all_tribes  = sorted(set(t for c in cards for t in c.get('tribes', [])))
    all_kw      = sorted(set(kw for c in cards for kw in extract_keywords(c.get('abilities', ''))))

    print(f"Classes: {len(all_classes)}, Types: {len(all_types)}, "
          f"Tribes: {len(all_tribes)}, Keywords: {len(all_kw)}, "
          f"Categories: {len(ALL_CATEGORIES)}")

    print("Building vectors...")
    vectors = [build_vector(c, all_classes, all_types, all_tribes, all_kw) for c in cards]

    print("Computing similarity matrix...")
    n = len(cards)
    rankings = []
    for i in range(n):
        sims = [(j, cosine_sim(vectors[i], vectors[j])) for j in range(n) if j != i]
        sims.sort(key=lambda x: -x[1])
        rankings.append([j for j, _ in sims])
        if i % 50 == 0:
            print(f"  {i}/{n}...")

    slim_cards = []
    for card in cards:
        kws = sorted(extract_keywords(card.get('abilities', '')))
        slim_cards.append({
            "name":     card['name'],
            "image":    card['image'],
            "cost":     card.get('cost') or 0,
            "strength": card.get('strength') or 0,
            "health":   card.get('health') or 0,
            "class":    card.get('class', ''),
            "type":     card.get('type', ''),
            "tribes":   card.get('tribes', []),
            "keywords": kws,
            "rarity":   card.get('rarity', ''),
            "set":      card.get('set', ''),
        })

    output = {"cards": slim_cards, "rankings": rankings}
    out_str = json.dumps(output, separators=(',', ':'))

    print(f"Writing {output_json}...")
    with open(output_json, 'w') as f:
        f.write(out_str)

    size_kb = len(out_str) / 1024
    print(f"Done! Output size: {size_kb:.0f} KB")

    # Sanity check
    sample_name = slim_cards[0]['name']
    top5 = [slim_cards[j]['name'] for j in rankings[0][:5]]
    print(f"\nSanity check — top 5 most similar to '{sample_name}':")
    for i, name in enumerate(top5):
        print(f"  #{i+2} {name}")


if __name__ == '__main__':
    import sys
    input_file  = sys.argv[1] if len(sys.argv) > 1 else 'cards.json'
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'game_data.json'
    generate(input_file, output_file)
