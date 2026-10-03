from atena_benchmark.routing import tier_for_role


def test_single_routes_every_role_to_strong():
    for role in ["architect", "planner", "implementer", "repair", "reviewer"]:
        assert tier_for_role("single", role) == "strong"


def test_hierarchical_routes_roles():
    assert tier_for_role("hierarchical", "architect") == "strong"
    assert tier_for_role("hierarchical", "reviewer") == "strong"
    assert tier_for_role("hierarchical", "planner") == "medium"
    assert tier_for_role("hierarchical", "implementer") == "weak"
    assert tier_for_role("hierarchical", "repair") == "weak"
