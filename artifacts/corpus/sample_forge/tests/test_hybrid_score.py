from sample_forge.hybrid_score import blend, min_max_norm


def test_blend_and_norm() -> None:
    assert blend(0.0, 1.0, alpha=0.5) == 0.5
    assert min_max_norm([2.0, 4.0, 6.0]) == [0.0, 0.5, 1.0]
