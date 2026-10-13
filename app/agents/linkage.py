"""Case similarity search (vector store) and the link-likelihood model.

Steps used to decide if two cases are linked:
  1. Text is turned into numbers (TF-IDF, then a small dense vector). FAISS (if installed) or
     NumPy finds the most similar cases quickly (the "vector store").
  2. For each candidate pair we measure 8 simple features (same suspect? same place? ...).
  3. A logistic-regression model turns the 8 features into a probability that the cases are linked.
"""
import math
from datetime import date

import numpy as np

FEATURES = ["text_similarity", "shared_suspect", "shared_person", "shared_place",
            "shared_exhibit", "same_offence", "same_station", "time_proximity"]

FEATURE_LABELS = {
    "text_similarity": "Similar wording of the narratives",
    "shared_suspect": "Same suspect name or alias",
    "shared_person": "Same other person (complainant/witness)",
    "shared_place": "Same place",
    "shared_exhibit": "Same exhibits or items",
    "same_offence": "Same type of offence",
    "same_station": "Same police station",
    "time_proximity": "Cases happened close in time",
}

THRESHOLD = 0.7   # probability above which two cases are shown as "possibly linked"
# chosen after testing 0.3-0.9 on simulated data: precision 0.76, recall 0.99 at 0.7
# (recall is prioritised over precision - missing a real link is worse than one extra
# recommendation for a human officer to review and reject)


# --------------------------------------------------------------------------- vector store
class VectorStore:
    def __init__(self, dims=48):
        self.dims = dims
        self.ids = []
        self.backend = "numpy"
        self.index = None
        self.svd = None

    def fit(self, ids, texts):
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize
        self.ids = list(ids)
        self.vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        self.X = self.vec.fit_transform(texts)
        n_docs, n_feat = self.X.shape
        k = min(self.dims, n_docs - 1, n_feat - 1)
        if k >= 2:
            self.svd = TruncatedSVD(n_components=k, random_state=0)
            emb = self.svd.fit_transform(self.X)
        else:
            self.svd = None
            emb = self.X.toarray()
        self.emb = normalize(emb).astype("float32")
        self.backend = "numpy"
        self.index = None
        try:
            import faiss
            self.index = faiss.IndexFlatIP(self.emb.shape[1])
            self.index.add(self.emb)
            self.backend = "faiss"
        except Exception:
            self.index = None
        return self

    def _embed(self, text):
        from sklearn.preprocessing import normalize
        q = self.vec.transform([text])
        e = self.svd.transform(q) if self.svd is not None else q.toarray()
        return normalize(e).astype("float32")

    def tfidf_similarity(self, text):
        """Cosine similarity between `text` and every stored case -> {case_id: value}."""
        from sklearn.metrics.pairwise import cosine_similarity
        sims = cosine_similarity(self.vec.transform([text]), self.X)[0]
        return {cid: float(s) for cid, s in zip(self.ids, sims)}

    def search(self, text, k=10, exclude=()):
        """Return the k most similar stored cases as [(case_id, score)]."""
        q = self._embed(text)
        want = min(len(self.ids), k + len(exclude) + 1)
        if self.index is not None:
            scores, idx = self.index.search(q, want)
            pairs = [(self.ids[i], float(s)) for s, i in zip(scores[0], idx[0]) if i >= 0]
        else:
            scores = (self.emb @ q[0])
            order = np.argsort(-scores)[:want]
            pairs = [(self.ids[i], float(scores[i])) for i in order]
        return [(cid, s) for cid, s in pairs if cid not in exclude][:k]


# --------------------------------------------------------------------------- features
def entity_sets(entities):
    persons = {e["normalized"] for e in entities if e["entity_type"] == "PERSON"}
    suspects = {e["normalized"] for e in entities if e["entity_type"] == "PERSON" and e.get("role") == "suspect"}
    places = {e["normalized"] for e in entities if e["entity_type"] == "PLACE"}
    exhibits = {e["normalized"] for e in entities if e["entity_type"] == "EXHIBIT"}
    return {"persons": persons, "suspects": suspects, "places": places, "exhibits": exhibits}


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _days_between(d1, d2):
    try:
        y1, m1, dd1 = [int(x) for x in d1[:10].split("-")]
        y2, m2, dd2 = [int(x) for x in d2[:10].split("-")]
        return abs((date(y1, m1, dd1) - date(y2, m2, dd2)).days)
    except Exception:
        return 365


def pair_features(case_a, sets_a, case_b, sets_b, text_sim):
    """Return (feature_vector_dict, evidence_dict) for a pair of cases."""
    shared_susp = (sets_a["suspects"] & sets_b["persons"]) | (sets_a["persons"] & sets_b["suspects"])
    shared_other = (sets_a["persons"] & sets_b["persons"]) - shared_susp
    shared_places = sets_a["places"] & sets_b["places"]
    shared_ex = sets_a["exhibits"] & sets_b["exhibits"]
    days = _days_between(case_a["reported_date"], case_b["reported_date"])
    feats = {
        "text_similarity": float(text_sim),
        "shared_suspect": 1.0 if shared_susp else 0.0,
        "shared_person": 1.0 if shared_other else 0.0,
        "shared_place": _jaccard(sets_a["places"], sets_b["places"]),
        "shared_exhibit": _jaccard(sets_a["exhibits"], sets_b["exhibits"]),
        "same_offence": 1.0 if case_a["offence_type"] == case_b["offence_type"] else 0.0,
        "same_station": 1.0 if case_a.get("station_id") == case_b.get("station_id") else 0.0,
        "time_proximity": math.exp(-days / 30.0),
    }
    evidence = {
        "suspects": sorted(shared_susp), "persons": sorted(shared_other),
        "places": sorted(shared_places), "exhibits": sorted(shared_ex), "days_apart": days,
    }
    return feats, evidence


def vector(feats):
    return [feats[f] for f in FEATURES]


# --------------------------------------------------------------------------- the model
class LinkModel:
    """Wraps a scikit-learn LogisticRegression plus the background data used for explanations."""

    def __init__(self, model, background, info):
        self.model = model
        self.background = np.array(background, dtype=float)
        self.mean = self.background.mean(axis=0)
        self.info = info

    def predict_proba_vec(self, X):
        return self.model.predict_proba(np.array(X, dtype=float))[:, 1]

    def probability(self, feats):
        return float(self.predict_proba_vec([vector(feats)])[0])

    def linear_contributions(self, feats):
        """Exact additive contribution of each feature to the log-odds, relative to the
        average training pair. For a linear model this equals the SHAP value."""
        x = np.array(vector(feats), dtype=float)
        coef = self.model.coef_[0]
        return {f: float(c * (xi - m)) for f, c, xi, m in zip(FEATURES, coef, x, self.mean)}

    def base_logodds(self):
        return float(self.model.intercept_[0] + np.dot(self.model.coef_[0], self.mean))


def train_model(X, y, info=None):
    from sklearn.linear_model import LogisticRegression
    X = np.array(X, dtype=float)
    y = np.array(y, dtype=int)
    clf = LogisticRegression(C=2.0, max_iter=2000, class_weight="balanced", random_state=0)
    clf.fit(X, y)
    rng = np.random.RandomState(0)
    take = rng.choice(len(X), size=min(300, len(X)), replace=False)
    info = dict(info or {})
    info.update({"n_pairs": int(len(y)), "n_linked_pairs": int(y.sum())})
    return LinkModel(clf, X[take], info)


def save_model(lm, path):
    import joblib
    joblib.dump({"model": lm.model, "background": lm.background, "info": lm.info}, path)


def load_model(path):
    """Load the saved model; if there is none, return a hand-set fallback so the system still works."""
    import os
    try:
        import joblib
        if os.path.exists(path):
            d = joblib.load(path)
            return LinkModel(d["model"], d["background"], d["info"])
    except Exception:
        pass
    return default_model()


def default_model():
    from sklearn.linear_model import LogisticRegression
    clf = LogisticRegression()
    clf.classes_ = np.array([0, 1])
    clf.coef_ = np.array([[3.0, 3.5, 1.0, 1.5, 1.5, 1.0, 0.5, 1.0]])
    clf.intercept_ = np.array([-7.0])
    bg = np.array([[0.1, 0.0, 0.0, 0.1, 0.1, 0.3, 0.3, 0.2]] * 5)
    return LinkModel(clf, bg, {"note": "default hand-set weights (no trained model found)"})
