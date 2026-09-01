from agent_surface.hatch import manifest_destination


def test_hatch_manifest_destination_is_in_distribution_metadata() -> None:
    assert (
        manifest_destination("example-operations", "1.2.3")
        == "example_operations-1.2.3.dist-info/agent-surface-operations.json"
    )
