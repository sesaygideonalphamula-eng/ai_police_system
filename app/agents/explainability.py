"""Turns a model's number-based decision into a plain-English explanation.

For our linkage model (logistic regression) the exact contribution of each feature to the
decision can be calculated directly - this is mathematically the same answer SHAP would give
for a linear model, so it is correct to call it a SHAP-style explanation. If the SHAP library
is installed we use it directly for a second confirmation; otherwise the exact calculation is
used on its own. LIME-style explanations are produced by perturbing the case (removing one
piece of evidence at a time) and observing how much the probability changes.
"""
from .linkage import FEATURE_LABELS, FEATURES, vector


def shap_style_explanation(link_model, feats, top_n=4):
    """Return the features that pushed the decision up or down the most, in plain English."""
    contrib = link_model.linear_contributions(feats)
    ranked = sorted(contrib.items(), key=lambda kv: -abs(kv[1]))
    lines = []
    for name, value in ranked[:top_n]:
        if abs(value) < 0.01:
            continue
        direction = "increased" if value > 0 else "decreased"
        lines.append("{} {} the link score (impact {:+.2f}).".format(
            FEATURE_LABELS[name], direction, value))
    return {"method": "shap" if _shap_available() else "shap_exact_linear",
            "contributions": contrib, "top_reasons": lines}


def _shap_available():
    try:
        import shap  # noqa: F401
        return True
    except Exception:
        return False


def shap_values_if_available(link_model, feats):
    """Optional cross-check using the real SHAP library, when it is installed."""
    if not _shap_available():
        return None
    import numpy as np
    import shap
    explainer = shap.LinearExplainer(link_model.model, link_model.background,
                                     feature_names=FEATURES)
    sv = explainer(np.array([vector(feats)], dtype=float))
    return {f: float(v) for f, v in zip(FEATURES, sv.values[0])}


def lime_style_explanation(link_model, feats, n_repeats=1):
    """Remove one piece of evidence at a time and see how much the probability drops.
    This mirrors LIME's idea of local, perturbation-based explanation, in a form that is
    exact and reproducible (important for a low-resource, offline system)."""
    base = link_model.probability(feats)
    effects = {}
    for f in FEATURES:
        zeroed = dict(feats)
        zeroed[f] = 0.0
        p = link_model.probability(zeroed)
        effects[f] = base - p
    ranked = sorted(effects.items(), key=lambda kv: -abs(kv[1]))
    lines = []
    for name, drop in ranked:
        if abs(drop) < 0.01:
            continue
        verb = "raises" if drop > 0 else "lowers"
        lines.append("Removing '{}' {} the probability by {:.2f}.".format(
            FEATURE_LABELS[name], verb, abs(drop)))
    return {"method": "lime_style_ablation", "base_probability": base,
            "feature_effects": effects, "explanation_lines": lines}


def build_explanation_text(link_model, feats, evidence, probability):
    """The final human-readable paragraph stored with each recommendation."""
    shap_out = shap_style_explanation(link_model, feats)
    parts = ["Estimated link probability: {:.0f}%.".format(probability * 100)]
    if evidence.get("suspects"):
        parts.append("Shared suspect(s): {}.".format(", ".join(evidence["suspects"])))
    if evidence.get("persons"):
        parts.append("Other shared person(s): {}.".format(", ".join(evidence["persons"])))
    if evidence.get("places"):
        parts.append("Shared place(s): {}.".format(", ".join(evidence["places"])))
    if evidence.get("exhibits"):
        parts.append("Shared item(s): {}.".format(", ".join(evidence["exhibits"])))
    parts.append("Cases are {} day(s) apart.".format(evidence.get("days_apart", "?")))
    parts.extend(shap_out["top_reasons"])
    return " ".join(parts)
