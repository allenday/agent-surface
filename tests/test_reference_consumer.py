import importlib
import inspect
from pathlib import Path

import pytest

from agent_surface import OperationError

DOMAIN_PATH = Path(__file__).parent / "reference_consumer" / "domain.py"
INTEGRATION_PATH = Path(__file__).parent / "reference_consumer" / "integration.py"


def load_domain():
    assert DOMAIN_PATH.is_file(), "reference consumer domain fixture is missing"
    return importlib.import_module("tests.reference_consumer.domain")


def load_integration():
    assert INTEGRATION_PATH.is_file(), "reference consumer integration fixture is missing"
    return importlib.import_module("tests.reference_consumer.integration")


def test_domain_fixture_is_consumer_owned() -> None:
    domain = load_domain()

    assert "agent_surface" not in DOMAIN_PATH.read_text()
    assert domain.LookupRequest.model_fields["ref"].annotation is domain.ResourceRef
    sensitive = domain.MutationRequest.model_fields["access_token"].json_schema_extra
    assert sensitive == {"sensitive": True}


def test_domain_service_supports_lookup_and_stable_errors() -> None:
    domain = load_domain()
    service = domain.Catalog.example()

    found = service.lookup(domain.LookupRequest(ref={"value": "resource-a"}))
    assert found.ref.value == "resource-a"
    assert found.label == "Alpha"

    with pytest.raises(domain.ResourceNotFound):
        service.lookup(domain.LookupRequest(ref={"value": "missing"}))


@pytest.mark.asyncio
async def test_domain_service_returns_a_bounded_page() -> None:
    domain = load_domain()
    service = domain.Catalog.example()

    page = await service.list_resources(domain.ListRequest(limit=1))

    assert [item.ref.value for item in page.items] == ["resource-a"]
    assert page.total == 2
    assert page.returned == 1
    assert page.truncated is True
    assert page.next_cursor == "resource-a"


def test_domain_mutation_requires_confirmation_and_never_returns_secret() -> None:
    domain = load_domain()
    service = domain.Catalog.example()
    request = domain.MutationRequest(
        ref={"value": "resource-a"},
        confirm=False,
        access_token="consumer-secret",
    )

    with pytest.raises(domain.ConfirmationRequired):
        service.mutate(request)
    assert "consumer-secret" not in repr(request)

    result = service.mutate(request.model_copy(update={"confirm": True}))
    assert result.changed is True
    assert "agent_surface" not in inspect.getsource(type(service))


def test_integration_registers_consumer_models_and_safety_metadata() -> None:
    domain = load_domain()
    integration = load_integration()
    app, _service = integration.build_app()

    definitions = {item.name: item for item in app.operations.list()}
    assert set(definitions) == {"resource.list", "resource.lookup", "resource.mutate"}
    assert definitions["resource.lookup"].input_model is domain.LookupRequest
    assert definitions["resource.lookup"].output_model is domain.ResourceRecord
    assert definitions["resource.lookup"].read_only is True
    assert definitions["resource.lookup"].idempotent is True
    assert definitions["resource.list"].input_model is domain.ListRequest
    assert definitions["resource.list"].output_model is domain.ResourcePage
    assert definitions["resource.list"].read_only is True
    assert definitions["resource.list"].idempotent is True
    assert definitions["resource.list"].open_world is True
    assert definitions["resource.mutate"].input_model is domain.MutationRequest
    assert definitions["resource.mutate"].output_model is domain.MutationResult
    assert definitions["resource.mutate"].destructive is True


def test_integration_registers_stable_resource_reference_codec() -> None:
    domain = load_domain()
    integration = load_integration()

    decoded = integration.build_references().decode_type(domain.ResourceRef, "resource-a")

    assert decoded == domain.ResourceRef(value="resource-a")


@pytest.mark.asyncio
async def test_integration_invokes_sync_async_and_destructive_operations() -> None:
    integration = load_integration()
    app, _service = integration.build_app()

    found = await app.invoke("resource.lookup", {"ref": {"value": "resource-a"}})
    page = await app.invoke("resource.list", {"limit": 1})
    changed = await app.invoke(
        "resource.mutate",
        {"ref": {"value": "resource-a"}, "confirm": True, "access_token": "secret"},
    )

    assert found.ref.value == "resource-a"
    assert page.returned == 1
    assert page.truncated is True
    assert changed.changed is True
    assert changed.revision == 2


@pytest.mark.asyncio
async def test_integration_translates_consumer_errors_at_the_boundary() -> None:
    integration = load_integration()
    app, _service = integration.build_app()

    with pytest.raises(OperationError) as missing:
        await app.invoke("resource.lookup", {"ref": {"value": "missing"}})
    assert missing.value.code == "resource_not_found"
    assert missing.value.details == ({"ref": "missing"},)

    with pytest.raises(OperationError) as confirmation:
        await app.invoke(
            "resource.mutate",
            {"ref": {"value": "resource-a"}, "confirm": False, "access_token": "secret"},
        )
    assert confirmation.value.code == "confirmation_required"
    assert confirmation.value.fix == "Set confirm=true after reviewing the target"
