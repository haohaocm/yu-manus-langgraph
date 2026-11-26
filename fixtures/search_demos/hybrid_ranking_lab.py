"""Hybrid ranking lab — sample code for CE-6 chunk + score demos."""


def explain_bm25() -> str:
    """BM25 ranks documents by term frequency with length normalization."""
    return "lexical score prefers overlapping tokens with the query"


def explain_embedding() -> str:
    """Embedding search compares vector directions with cosine similarity."""
    return "semantic score prefers similar meaning even with different words"


def explain_hybrid(alpha: float = 0.5) -> str:
    """
    Hybrid mixes normalized BM25 and embedding scores.

    alpha is the weight on embedding; (1 - alpha) stays on BM25.
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha must be between 0 and 1")
    return f"hybrid uses alpha={alpha} for embedding weight"


def detect_path_escape(user_path: str) -> bool:
    """Return True when user_path looks like a workspace escape attempt."""
    normalized = user_path.replace("\\", "/")
    return normalized.startswith("../") or "/../" in normalized


def demo_helper_alpha() -> str:
    return "alpha balances lexical and semantic evidence"


def demo_helper_beta() -> str:
    return "beta is unused here; kept only to pad the file for chunk windows"


def demo_helper_gamma() -> str:
    return "gamma padding line for multi-chunk demos"


def demo_helper_delta() -> str:
    return "delta padding line for multi-chunk demos"


def demo_helper_epsilon() -> str:
    return "epsilon padding line for multi-chunk demos"


def demo_helper_zeta() -> str:
    return "zeta padding line for multi-chunk demos"


def demo_helper_eta() -> str:
    return "eta padding line for multi-chunk demos"


def demo_helper_theta() -> str:
    return "theta padding line for multi-chunk demos"


def demo_helper_iota() -> str:
    return "iota padding line for multi-chunk demos"


def demo_helper_kappa() -> str:
    return "kappa padding line for multi-chunk demos"


def demo_helper_lambda() -> str:
    return "lambda padding line for multi-chunk demos"


def demo_helper_mu() -> str:
    return "mu padding line for multi-chunk demos"


def demo_helper_nu() -> str:
    return "nu padding line for multi-chunk demos"


def demo_helper_xi() -> str:
    return "xi padding line for multi-chunk demos"


def demo_helper_omicron() -> str:
    return "omicron padding line for multi-chunk demos"


def demo_helper_pi() -> str:
    return "pi padding line for multi-chunk demos"


def demo_helper_rho() -> str:
    return "rho padding line for multi-chunk demos"


def demo_helper_sigma() -> str:
    return "sigma padding line for multi-chunk demos"


def demo_helper_tau() -> str:
    return "tau padding line for multi-chunk demos"


def demo_helper_upsilon() -> str:
    return "upsilon padding line for multi-chunk demos"


def demo_helper_phi() -> str:
    return "phi padding line for multi-chunk demos"


def demo_helper_chi() -> str:
    return "chi padding line for multi-chunk demos"


def demo_helper_psi() -> str:
    return "psi padding line for multi-chunk demos"


def demo_helper_omega() -> str:
    return "omega padding line for multi-chunk demos"


if __name__ == "__main__":
    print(explain_hybrid(0.5))
    print(detect_path_escape("../secret"))
