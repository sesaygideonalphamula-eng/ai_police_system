"""Creates SIMULATED police case records (no real people, no real cases).

The proposal says the system is tested on simulated / anonymised data. This module writes
realistic-looking narratives from templates. Some cases belong to a hidden "series"
(the same suspect or method), so we know the true answer when we test case linkage.
"""
import random
from datetime import date, timedelta

STATIONS = [
    {"name": "Central Division", "code": "CEN", "patrol_officers": 24, "investigators": 8, "coverage_weight": 1.4,
     "places": ["Fort Street", "Tengbeh Town", "Congo Town", "Cline Town", "Kroo Bay", "Circular Road"]},
    {"name": "East Division (Kissy)", "code": "EST", "patrol_officers": 20, "investigators": 6, "coverage_weight": 1.3,
     "places": ["Kissy", "Fourah Bay", "Mountain Cut", "Allen Town", "Ferry Junction", "Old Railway Line"]},
    {"name": "West Division (Lumley)", "code": "WST", "patrol_officers": 18, "investigators": 6, "coverage_weight": 1.1,
     "places": ["Lumley", "Aberdeen", "Murray Town", "Goderich", "Hill Station", "Brookfields"]},
    {"name": "Wellington Division", "code": "WEL", "patrol_officers": 14, "investigators": 4, "coverage_weight": 0.9,
     "places": ["Wellington", "Calaba Town", "Portee", "Juba", "Regent", "Grafton"]},
    {"name": "Waterloo Division", "code": "WAT", "patrol_officers": 12, "investigators": 4, "coverage_weight": 0.8,
     "places": ["Waterloo", "Hastings", "Newton", "Lakka", "Tombo", "Macdonald"]},
]

FIRST = ["Mohamed", "Abdul", "Ibrahim", "Alusine", "Sahr", "Foday", "Musa", "Sorie", "Idrissa", "Brima",
         "Santigie", "Mariama", "Fatmata", "Aminata", "Isatu", "Hawa", "Kadiatu", "Salamatu", "Zainab", "Marie"]
LAST = ["Kamara", "Sesay", "Koroma", "Bangura", "Conteh", "Turay", "Kanu", "Jalloh", "Bah", "Sankoh",
        "Mansaray", "Fofanah", "Dumbuya", "Kallon", "Lahai", "Thomas", "Cole", "Johnson", "Williams", "Davies"]
ALIASES = ["Small Boy", "Black Rat", "Skido", "Killer B", "Kush", "Gaza", "Slim Shady", "Tall Man",
           "Redman", "Boss Man", "Sharp Sharp", "Junior Bad"]

WEAPONS = ["machete", "cutlass", "knife", "pistol", "iron rod", "locally made gun", "crowbar", "hammer"]
ITEMS = ["mobile phone", "laptop", "television", "generator", "gold chain", "handbag", "cash",
         "solar panel", "car battery", "bicycle"]

OFFENCES = {
    "Armed Robbery": 3, "Housebreaking": 2, "Motorcycle Theft": 2, "Larceny": 1,
    "Fraud": 2, "Assault": 2, "Drug Possession": 1,
}
SERIES_OFFENCES = ["Armed Robbery", "Housebreaking", "Motorcycle Theft", "Larceny", "Fraud", "Assault",
                   "Housebreaking", "Armed Robbery", "Motorcycle Theft", "Larceny", "Housebreaking", "Assault"]

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]
SOLVED_NOTES = [
    "Suspect arrested after a tip from the community watch; recovered property returned to the owner.",
    "Suspect identified from witness statements and arrested; case sent for prosecution.",
    "Suspect traced through recovered exhibit; charged and taken to court.",
    "Property recovered at a second-hand market after a patrol check; suspect arrested.",
]
TODAY = date(2026, 9, 28)


def _fmt_date(rng, d):
    style = rng.choice(["dmy", "dmy", "mdy", "iso", "slash"])
    if style == "dmy":
        return "{} {} {}".format(d.day, MONTH_NAMES[d.month - 1], d.year)
    if style == "mdy":
        return "{} {}, {}".format(MONTH_NAMES[d.month - 1], d.day, d.year)
    if style == "iso":
        return d.isoformat()
    return "{:02d}/{:02d}/{}".format(d.day, d.month, d.year)


def _time_text(rng, daypart):
    if daypart == "night":
        h, ap = rng.choice([(11, "pm"), (12, "am"), (1, "am"), (2, "am"), (3, "am")])
    elif daypart == "evening":
        h, ap = rng.choice([(6, "pm"), (7, "pm"), (8, "pm"), (9, "pm")])
    elif daypart == "morning":
        h, ap = rng.choice([(6, "am"), (7, "am"), (8, "am"), (9, "am")])
    else:
        h, ap = rng.choice([(12, "pm"), (1, "pm"), (2, "pm"), (3, "pm")])
    return "{}:{:02d} {}".format(h, rng.choice([0, 10, 15, 20, 30, 40, 45]), ap)


def _name(rng, used=None):
    while True:
        n = "{} {}".format(rng.choice(FIRST), rng.choice(LAST))
        if used is None or n not in used:
            if used is not None:
                used.add(n)
            return n


def _norm(name):
    return name.lower()


def _build_case(rng, offence, station, when, daypart, suspect, alias, place, weapon, item,
                solved, used_names, show_suspect_mode):
    """Write one narrative and return (case dict, ground-truth sets)."""
    gt = {"persons": set(), "places": set(), "exhibits": set(), "dates": set()}
    if offence == "Housebreaking" and weapon in ("pistol", "locally made gun", "knife"):
        weapon = "crowbar"
    comp = _name(rng, used_names)
    witness = _name(rng, used_names)
    comp_mode = rng.random()
    if comp_mode < 0.85:
        comp_text = "the complainant, {}".format(comp)
        gt["persons"].add(_norm(comp))
    else:
        surname = comp.split()[1]
        comp_text = "the complainant, Mr. {}".format(surname)
        gt["persons"].add(_norm(surname))
    when_text = _fmt_date(rng, when)
    gt["dates"].add(when.isoformat())
    time_text = _time_text(rng, daypart)
    gt["places"].add(place.lower())

    if offence == "Armed Robbery":
        gt["exhibits"].update([weapon.lower(), item.lower()])
        core = ("reported that armed men attacked {} at {} and took a {} at gunpoint, threatening "
                "the victim with a {}.").format("the victim", place, item, weapon)
    elif offence == "Housebreaking":
        gt["exhibits"].update([item.lower(), weapon.lower()])
        core = ("reported that unknown persons forced open the door of a house at {} using a {} "
                "and stole a {}.").format(place, weapon, item)
    elif offence == "Motorcycle Theft":
        plate = "{}{} {}".format(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ"), rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ"),
                                 rng.randint(100, 999))
        plate = "A" + plate  # three letters starting with A
        core = ("reported that a motorbike with registration number {} was stolen while parked near "
                "{}.").format(plate, place)
        gt["exhibits"].update(["motorbike", "vehicle plate " + plate.lower()])
        if rng.random() < 0.5:
            core += " A bolt cutter was found at the scene."
            gt["exhibits"].add("bolt cutter")
    elif offence == "Larceny":
        gt["exhibits"].add(item.lower())
        core = "reported that a {} was stolen from a shop at {}.".format(item, place)
    elif offence == "Fraud":
        gt["exhibits"].update([item.lower()])
        core = ("reported that a person collected cash as payment for a {} that was never "
                "delivered; the meeting took place at {}.").format(item, place)
        gt["exhibits"].add("cash")
    elif offence == "Assault":
        gt["exhibits"].add(weapon.lower())
        core = "reported that the victim was attacked and beaten with a {} at {}.".format(weapon, place)
    else:  # Drug Possession
        gt["exhibits"].add("cannabis")
        core = ("said officers on patrol at {} searched a suspect and found a quantity of cannabis "
                "wrapped in paper.").format(place)
        comp_text = "the reporting officer"
        gt["persons"].discard(_norm(comp))
        gt["persons"].discard(_norm(comp.split()[1]))

    sep = " " if offence == "Drug Possession" else ", "
    sentences = ["On {}, at about {}, {}{}{}".format(when_text, time_text, comp_text, sep, core)]

    # suspect information
    if suspect and show_suspect_mode == "full":
        sentences.append('A witness described the suspect, {}, alias "{}", who lives in the area.'.format(suspect, alias))
        gt["persons"].update([_norm(suspect), _norm(alias)])
    elif suspect and show_suspect_mode == "name":
        sentences.append("The suspect was identified as {} by residents.".format(suspect))
        gt["persons"].add(_norm(suspect))
    elif suspect and show_suspect_mode == "alias":
        sentences.append('The suspect is known as "{}" in the area.'.format(alias))
        gt["persons"].add(_norm(alias))
    else:
        sentences.append("The suspect fled and has not yet been identified.")

    # witness statement (sometimes without a cue word)
    d2 = when + timedelta(days=1)
    if rng.random() < 0.6:
        sentences.append("The following day, officers visited {} and recorded a statement from witness {}.".format(place, witness))
        gt["persons"].add(_norm(witness))
    elif rng.random() < 0.7:
        sentences.append("The following day, {}, a trader nearby, told officers that he heard the noise.".format(witness))
        # this style has no role cue, so the rule-based extractor may miss it (a hard case)
        gt["persons"].add(_norm(witness))
    else:
        sentences.append("The following day, officers visited the scene.")

    outcome = None
    if solved:
        d3 = when + timedelta(days=rng.randint(5, 20))
        gt["dates"].add(d3.isoformat())
        arrested = suspect if suspect else _name(rng, used_names)
        sentences.append("On {}, officers arrested {} at {} and recovered a {}.".format(
            d3.isoformat(), arrested, place, item))
        gt["persons"].add(_norm(arrested))
        gt["exhibits"].add(item.lower())
        outcome = rng.choice(SOLVED_NOTES)
    return {"narrative": " ".join(sentences), "outcome_note": outcome}, gt


def generate(seed=42, n_series=12, n_single=32):
    rng = random.Random(seed)
    used = set()
    cases = []

    def add(offence, station, when, daypart, suspect, alias, place, weapon, item, status, series, mode):
        solved = status == "Solved"
        body, gt = _build_case(rng, offence, station, when, daypart, suspect, alias, place,
                               weapon, item, solved, used, mode)
        cases.append({
            "title": "{} at {}".format(offence, place),
            "offence_type": offence,
            "priority": OFFENCES[offence] if offence != "Assault" else rng.choice([2, 3]),
            "status": status,
            "station_code": station["code"],
            "location": place,
            "reported_date": when.isoformat(),
            "narrative": body["narrative"],
            "outcome_note": body["outcome_note"],
            "series": series,
            "gt": gt,
        })

    # ---- crime series (linked cases)
    for i in range(n_series):
        offence = SERIES_OFFENCES[i % len(SERIES_OFFENCES)]
        station = STATIONS[i % len(STATIONS)]
        suspect = _name(rng, used)
        alias = ALIASES[i % len(ALIASES)]
        home = rng.sample(station["places"], 2)
        weapon = rng.choice(WEAPONS)
        item = rng.choice(ITEMS)
        daypart = rng.choice(["night", "night", "evening"])
        start = date(2026, 5, 1) + timedelta(days=rng.randint(0, 100))
        size = rng.choice([3, 4, 4, 5, 6])
        when = start
        for k in range(size):
            if when > date(2026, 9, 25):
                break
            r = rng.random()
            mode = "full" if r < 0.45 else "name" if r < 0.7 else "alias" if r < 0.9 else "none"
            place = home[0] if rng.random() < 0.7 else (home[1] if rng.random() < 0.7 else rng.choice(station["places"]))
            w = weapon if rng.random() < 0.75 else rng.choice(WEAPONS)
            it = item if rng.random() < 0.7 else rng.choice(ITEMS)
            status = rng.choice(["Under Investigation", "Under Investigation", "Open", "Solved"])
            add(offence, station, when, daypart, suspect, alias, place, w, it, status, "S%02d" % (i + 1), mode)
            when = when + timedelta(days=rng.randint(3, 16))

    # ---- single cases (not linked to anything)
    for j in range(n_single):
        offence = rng.choice(list(OFFENCES.keys()))
        station = rng.choice(STATIONS)
        when = date(2026, 5, 1) + timedelta(days=rng.randint(0, 145))
        suspect = _name(rng, used) if rng.random() < 0.6 else None
        alias = rng.choice(ALIASES) if suspect and rng.random() < 0.3 else None
        mode = "none" if not suspect else ("full" if alias else "name")
        if suspect and alias is None:
            alias = "-"
        status = rng.choices(["Open", "Under Investigation", "Solved", "Closed"], weights=[4, 3, 2, 1])[0]
        if status == "Solved" and not suspect:
            suspect = _name(rng, used)
            mode = "name"
        add(offence, station, when, rng.choice(["night", "evening", "morning", "afternoon"]),
            suspect, alias, rng.choice(station["places"]), rng.choice(WEAPONS), rng.choice(ITEMS),
            status, None, mode)

    cases.sort(key=lambda c: c["reported_date"])
    return {"stations": STATIONS, "cases": cases}
