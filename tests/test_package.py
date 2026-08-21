def test_package_exposes_version() -> None:
    import agent_surface

    assert agent_surface.__version__ == "0.1.1"


def test_package_exposes_bounded_rendering_api() -> None:
    import agent_surface

    assert agent_surface.BoundedCollection
    assert agent_surface.OutputBudget
    assert agent_surface.RenderOptions
    assert callable(agent_surface.render)
    assert callable(agent_surface.render_envelope)
