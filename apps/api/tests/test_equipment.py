import uuid

import pytest

from alessio_api.seed import seed_demo


def base(org_id):
    return f"/api/v1/platform/organizations/{org_id}"


@pytest.fixture
def contract(staff_client, demo):
    response = staff_client.post(
        f"{base(demo.organization_id)}/contracts",
        json={"number": "CT-2026-001", "starts_on": "2026-10-01"},
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


def add(staff_client, org_id, **fields):
    return staff_client.post(f"{base(org_id)}/equipment", json=fields)


def test_only_alessio_staff_reaches_the_platform_area(client, client_as, demo):
    assert client.get("/api/v1/platform/organizations").status_code == 403
    assert (
        client.post(
            f"{base(demo.organization_id)}/contracts",
            json={"number": "X", "starts_on": "2026-10-01"},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/me").json()["is_platform_staff"] is False


def test_mixed_ownership_in_the_same_client(staff_client, client, demo, contract):
    own = add(
        staff_client,
        demo.organization_id,
        kind="camera",
        ownership="client",
        brand="Intelbras",
        camera_id=str(demo.camera_id),
    )
    assert own.status_code == 201, own.text
    loan = add(
        staff_client,
        demo.organization_id,
        kind="agent_host",
        ownership="comodato",
        contract_id=contract["id"],
        brand="Beelink",
        model="Mini S12",
        serial_number="BL-123",
        agent_id=str(demo.agent_id),
        monthly_fee_cents=15000,
        reference_value_cents=250000,
        delivered_on="2026-10-02",
    )
    assert loan.status_code == 201, loan.text
    summary = loan.json()["summary"]
    assert summary == {
        "total": 2,
        "client_owned": 1,
        "comodato": 1,
        "comodato_monthly_cents": 15000,
        "comodato_reference_cents": 250000,
    }

    # O administrador do cliente consulta a mesma lista.
    seen = client.get("/api/v1/equipment").json()
    assert seen["summary"] == summary
    by_kind = {item["kind"]: item for item in seen["items"]}
    assert by_kind["camera"]["camera_name"] == "Entrada"
    assert by_kind["agent_host"]["contract_number"] == "CT-2026-001"
    assert by_kind["agent_host"]["agent_name"] == "agente-demo"

    [overview] = [
        o
        for o in staff_client.get("/api/v1/platform/organizations").json()
        if o["id"] == str(demo.organization_id)
    ]
    assert overview["summary"]["comodato_monthly_cents"] == 15000
    assert overview["active_contracts"] == 1


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"kind": "camera", "ownership": "comodato"}, "precisa de um contrato"),
        (
            {"kind": "camera", "ownership": "client", "monthly_fee_cents": 100},
            "não tem contrato nem valor mensal",
        ),
        (
            {"kind": "camera", "ownership": "client", "reference_value_cents": -1},
            "greater than or equal",
        ),
    ],
)
def test_ownership_rules_are_enforced(staff_client, demo, fields, message):
    response = add(staff_client, demo.organization_id, **fields)
    assert response.status_code == 422
    assert message in response.text


def test_links_must_belong_to_the_same_client(staff_client, session, demo, contract):
    other = seed_demo(session, uuid.uuid4(), "alg_outra", org_name="Outra")
    foreign_camera = add(
        staff_client,
        demo.organization_id,
        kind="camera",
        ownership="client",
        camera_id=str(other.camera_id),
    )
    assert foreign_camera.status_code == 422
    foreign_contract = add(
        staff_client,
        other.organization_id,
        kind="camera",
        ownership="comodato",
        contract_id=contract["id"],
    )
    assert foreign_contract.status_code == 422
    # E a outra organização não enxerga os equipamentos desta.
    add(staff_client, demo.organization_id, kind="ups", ownership="client")
    assert staff_client.get(f"{base(other.organization_id)}/equipment").json()["items"] == []


def test_duplicate_contract_number_is_refused(staff_client, demo, contract):
    again = staff_client.post(
        f"{base(demo.organization_id)}/contracts",
        json={"number": "CT-2026-001", "starts_on": "2026-10-05"},
    )
    assert again.status_code == 409


def test_ending_a_contract_lists_what_must_be_returned(staff_client, demo, contract):
    created = add(
        staff_client,
        demo.organization_id,
        kind="agent_host",
        ownership="comodato",
        contract_id=contract["id"],
        monthly_fee_cents=9900,
    )
    equipment = created.json()["items"][0]

    contracts = staff_client.post(
        f"{base(demo.organization_id)}/contracts/{contract['id']}/end",
        json={"ends_on": "2026-12-31"},
    ).json()
    assert contracts[0]["status"] == "ended"
    assert contracts[0]["pending_return"] == 1

    # Contrato encerrado não recebe equipamento novo.
    refused = add(
        staff_client,
        demo.organization_id,
        kind="camera",
        ownership="comodato",
        contract_id=contract["id"],
    )
    assert refused.status_code == 422

    # Registrar a devolução zera a pendência e tira o item do resumo.
    payload = {k: equipment[k] for k in ("kind", "ownership", "contract_id", "monthly_fee_cents")}
    returned = staff_client.patch(
        f"{base(demo.organization_id)}/equipment/{equipment['id']}",
        json={**payload, "status": "returned"},
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["items"][0]["returned_on"] is not None
    assert returned.json()["summary"]["comodato"] == 0
    contracts = staff_client.get(f"{base(demo.organization_id)}/contracts").json()
    assert contracts[0]["pending_return"] == 0


def test_viewer_cannot_see_equipment(client_as):
    assert client_as("viewer").get("/api/v1/equipment").status_code == 403
    assert client_as("admin").get("/api/v1/equipment").status_code == 200


def test_staff_commands(session, demo):
    from alessio_api.admin import set_platform_staff

    user = set_platform_staff(session, "DONA@example.com", True)
    assert user.is_platform_staff is True
    with pytest.raises(LookupError):
        set_platform_staff(session, "ninguem@example.com", True)
