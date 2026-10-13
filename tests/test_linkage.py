from app.agents import linkage


def test_identical_suspect_gives_high_probability():
    lm = linkage.default_model()
    feats = {"text_similarity": 0.6, "shared_suspect": 1.0, "shared_person": 0.0,
             "shared_place": 0.5, "shared_exhibit": 0.3, "same_offence": 1.0,
             "same_station": 1.0, "time_proximity": 0.8}
    unrelated = {"text_similarity": 0.05, "shared_suspect": 0.0, "shared_person": 0.0,
                "shared_place": 0.0, "shared_exhibit": 0.0, "same_offence": 0.0,
                "same_station": 0.0, "time_proximity": 0.1}
    assert lm.probability(feats) > lm.probability(unrelated)
    assert lm.probability(feats) >= 0.5


def test_jaccard_helper():
    assert linkage._jaccard({"a", "b"}, {"b", "c"}) == 1 / 3
    assert linkage._jaccard(set(), {"a"}) == 0.0
