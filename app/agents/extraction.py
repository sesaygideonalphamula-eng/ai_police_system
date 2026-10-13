"""Reads a case narrative and pulls out people, places, dates and exhibits.

Two methods are used together:
  1. Rules (regular expressions + a list of Sierra Leone place names) - always available.
  2. spaCy named-entity recognition - used only if spaCy and its English model are installed.
"""
import re
from datetime import date

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
MONTH_RE = (r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
            r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")

LOCALITIES = [
    "Congo Town", "Murray Town", "Hill Station", "Calaba Town", "Tengbeh Town",
    "Fourah Bay", "Mountain Cut", "Cline Town", "Kroo Bay", "Susan's Bay", "Allen Town",
    "Ferry Junction", "Old Railway Line", "Kissy", "Wellington", "Aberdeen", "Lumley",
    "Goderich", "Brookfields", "Waterloo", "Grafton", "Regent", "Gloucester", "Leicester",
    "Wilberforce", "Portee", "Lakka", "Juba", "Macdonald", "Tombo", "Hastings", "Newton",
    "Bo", "Kenema", "Makeni", "Koidu", "Lunsar", "Port Loko", "Kabala", "Magburaka",
    "Freetown", "Bumbuna", "Kailahun", "Moyamba", "Pujehun", "Bonthe",
]
# these are too general to help link two cases, so they are ignored as places
GENERIC_PLACES = {"freetown"}

EXHIBITS = [
    "machete", "cutlass", "knife", "pistol", "shotgun", "locally made gun", "iron rod",
    "hammer", "crowbar", "screwdriver", "mobile phone", "laptop", "television", "generator",
    "motorbike", "motorcycle", "okada", "tricycle", "keh-keh", "gold chain", "handbag",
    "cash", "fuel", "solar panel", "car battery", "bicycle", "wire cable", "sack of rice",
    "ATM card", "forged cheque", "sim card", "counterfeit notes", "cannabis", "bolt cutter",
]

TITLES = r"(?:Mr|Mrs|Ms|Miss|Dr|Alhaji|Alhaja|Pa|Mama|Sgt|Sergeant|Inspector|Constable)"
NAME = r"[A-Z][a-z'\-]+(?:\s+[A-Z][a-z'\-]+){0,2}"
STOP_WORDS = {"The", "Then", "On", "At", "In", "When", "He", "She", "They", "It", "A", "An",
              "After", "Before", "During", "While", "That", "This", "Police", "Officers",
              "Station", "Later", "Following", "According", "Upon", "Both", "And", "But",
              "Who", "Which", "Where", "From", "With", "Also", "There", "His", "Her"}

ROLE_CUES = [
    ("suspect", r"(?:suspects?|accused|arrested|identified as|apprehended|culprit)"),
    ("complainant", r"(?:complainants?|victims?)"),
    ("witness", r"(?:witness(?:es)?)"),
]
ROLE_RANK = {"suspect": 3, "complainant": 2, "witness": 1, "person": 0}


# ---------------------------------------------------------------- helpers
def clean_name(raw):
    """Remove stop words from the end/start of a captured name."""
    toks = raw.split()
    while toks and toks[-1] in STOP_WORDS:
        toks.pop()
    while toks and toks[0] in STOP_WORDS:
        toks.pop(0)
    return " ".join(toks)


def normalize_person(text):
    t = re.sub(r"\b" + TITLES + r"\.?\s+", "", text.strip(), flags=re.I)
    t = re.sub(r"[^a-zA-Z' \-]", "", t).lower()
    return re.sub(r"\s+", " ", t).strip()


def find_dates(text):
    """Return a list of (position, 'YYYY-MM-DD') for every explicit date in the text."""
    found = []
    patterns = [
        (r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + MONTH_RE + r"[a-z]*\.?,?\s+(\d{4})\b", "dmy"),
        (r"\b" + MONTH_RE + r"[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", "mdy"),
        (r"\b(\d{4})-(\d{2})-(\d{2})\b", "iso"),
        (r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", "slash"),
    ]
    for pat, kind in patterns:
        for m in re.finditer(pat, text):
            try:
                if kind == "dmy":
                    d = date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
                elif kind == "mdy":
                    d = date(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
                elif kind == "iso":
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                else:
                    d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                found.append((m.start(), d.isoformat()))
            except ValueError:
                continue
    found.sort()
    return found


def _role_before(text, pos):
    """Look at the few words before a name to decide its role."""
    window = text[max(0, pos - 30):pos]
    best = "person"
    for role, cue in ROLE_CUES:
        m = list(re.finditer(cue, window, flags=re.I))
        if m and ROLE_RANK[role] > ROLE_RANK[best]:
            best = role
    return best


# ---------------------------------------------------------------- spaCy (optional)
_NLP = None
_NLP_TRIED = False


def spacy_status():
    global _NLP, _NLP_TRIED
    if not _NLP_TRIED:
        _NLP_TRIED = True
        try:
            import spacy
            _NLP = spacy.load("en_core_web_sm")
        except Exception:
            _NLP = None
    return "available" if _NLP is not None else "not installed (rule-based extraction only)"


def _spacy_entities(text):
    if spacy_status() != "available":
        return []
    out = []
    doc = _NLP(text)
    for ent in doc.ents:
        if ent.label_ == "PERSON" and len(ent.text.split()) >= 2:
            out.append(("PERSON", ent.text.strip(), "person"))
        elif ent.label_ in ("GPE", "LOC", "FAC") and len(ent.text) > 2:
            out.append(("PLACE", ent.text.strip(), None))
    return out


# ---------------------------------------------------------------- main function
def extract_entities(text, use_spacy=True):
    """Return a list of dicts: entity_type, value, normalized, role, source."""
    people = {}   # normalized -> dict
    others = {}

    def add_person(value, role, source):
        norm = normalize_person(value)
        if not norm or len(norm) < 3:
            return
        cur = people.get(norm)
        if cur is None or ROLE_RANK[role] > ROLE_RANK[cur["role"]]:
            people[norm] = {"entity_type": "PERSON", "value": value.strip(), "normalized": norm,
                            "role": role, "source": source}

    # ---- people: role cue + name
    for role, cue in ROLE_CUES:
        # the cue word may be in any letter case, but the name itself must start with capitals
        pat = r"(?i:\b" + cue + r"\b)[,:]?\s+(?:" + TITLES + r"\.?\s+)?(" + NAME + r")"
        for m in re.finditer(pat, text):
            add_person(clean_name(m.group(1)), role, "rule")
    # ---- people: titled names (Mr. Kamara)
    for m in re.finditer(r"\b" + TITLES + r"\.?\s+(" + NAME + r")", text):
        name = clean_name(m.group(1))
        if name:
            add_person(name, _role_before(text, m.start()), "rule")
    # ---- aliases in quotes
    for m in re.finditer(r"(?i:alias|a\.k\.a\.?|also known as|popularly known as|known as|nicknamed)"
                         r"\s+[\"“'‘]([^\"”'’]{2,30})[\"”'’]", text):
        add_person(m.group(1), "suspect", "rule-alias")

    result = list(people.values())

    # ---- places
    places = {}
    for name in LOCALITIES:
        if re.search(r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])", text):
            places[name.lower()] = name
    for m in re.finditer(r"\b((?:[A-Z][a-z]+\s){1,2}(?:Street|Road|Junction|Market|Lane|Bridge|"
                         r"Estate|Village|Roundabout|Wharf|Ground|Corner))\b", text):
        nm = clean_name(m.group(1))
        if nm and len(nm.split()) >= 2:
            places[nm.lower()] = nm
    for norm, val in places.items():
        if norm in GENERIC_PLACES:
            continue
        result.append({"entity_type": "PLACE", "value": val, "normalized": norm,
                       "role": None, "source": "rule"})

    # ---- dates
    seen_dates = set()
    for _, iso in find_dates(text):
        if iso not in seen_dates:
            seen_dates.add(iso)
            result.append({"entity_type": "DATE", "value": iso, "normalized": iso,
                           "role": None, "source": "rule"})

    # ---- exhibits
    seen_ex = set()
    for item in EXHIBITS:
        if re.search(r"\b" + re.escape(item) + r"s?\b", text, flags=re.I):
            seen_ex.add(item.lower())
    for m in re.finditer(r"\b([A-Z]{3})\s?-?(\d{3})\b", text):
        seen_ex.add("vehicle plate {} {}".format(m.group(1), m.group(2)).lower())
    for m in re.finditer(r"\bIMEI[:\s]*(\d{10,})", text, flags=re.I):
        seen_ex.add("imei " + m.group(1))
    for ex in sorted(seen_ex):
        result.append({"entity_type": "EXHIBIT", "value": ex, "normalized": ex,
                       "role": None, "source": "rule"})

    # ---- optional spaCy additions
    if use_spacy:
        have_people = set(people.keys())
        have_places = set(places.keys())
        for etype, val, role in _spacy_entities(text):
            if etype == "PERSON":
                norm = normalize_person(val)
                if norm and norm not in have_people and not any(norm in p or p in norm for p in have_people):
                    have_people.add(norm)
                    result.append({"entity_type": "PERSON", "value": val, "normalized": norm,
                                   "role": "person", "source": "spacy"})
            else:
                norm = val.lower()
                if norm not in have_places and norm not in GENERIC_PLACES:
                    have_places.add(norm)
                    result.append({"entity_type": "PLACE", "value": val, "normalized": norm,
                                   "role": None, "source": "spacy"})
    return result
