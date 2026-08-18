import importlib
import inspect
from pathlib import Path

import pytest

DOMAIN_PATH = Path(__file__).parent / "reference_consumer" / "domain.py"


def load_domain():
    assert DOMAIN_PATH.is_file(), "reference consumer domain fixture is missing"
    return importlib.import_module("tests.reference_consumer.domain")


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

    result = service.mutate(request.model_copy(update={"confirm": True}))
    assert result.changed is True
    assert "consumer-secret" not in repr(result)
    assert "agent_surface" not in inspect.getsource(type(service))
