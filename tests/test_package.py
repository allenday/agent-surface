def test_package_exposes_version() -> None:
    import agent_surface

    assert agent_surface.__version__ == "0.1.0"
