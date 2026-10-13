from app.agents.extraction import extract_entities, find_dates


def test_finds_suspect_and_complainant():
    text = ("The complainant, John Bangura, reported that the suspect, Mohamed Kamara, "
            "attacked him at Congo Town with a knife on 3 June 2026.")
    ents = extract_entities(text, use_spacy=False)
    people = {(e["normalized"], e["role"]) for e in ents if e["entity_type"] == "PERSON"}
    assert ("john bangura", "complainant") in people
    assert ("mohamed kamara", "suspect") in people


def test_finds_alias():
    text = 'The suspect, alias "Small Boy", was seen fleeing the scene.'
    ents = extract_entities(text, use_spacy=False)
    values = {e["normalized"] for e in ents if e["entity_type"] == "PERSON"}
    assert "small boy" in values


def test_finds_place_and_exhibit():
    text = "The robbery happened at Lumley and a mobile phone was taken."
    ents = extract_entities(text, use_spacy=False)
    types = {(e["entity_type"], e["normalized"]) for e in ents}
    assert ("PLACE", "lumley") in types
    assert ("EXHIBIT", "mobile phone") in types


def test_finds_dates_in_multiple_formats():
    assert find_dates("It happened on 3 June 2026.")[0][1] == "2026-06-03"
    assert find_dates("It happened on June 3, 2026.")[0][1] == "2026-06-03"
    assert find_dates("It happened on 2026-06-03.")[0][1] == "2026-06-03"
    assert find_dates("It happened on 03/06/2026.")[0][1] == "2026-06-03"
