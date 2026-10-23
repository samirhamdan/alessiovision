"""Cadastro completo pela Plataforma: cliente → contrato → local → agente → câmera."""

import pytest
from fastapi.testclient import TestClient

from alessio_api.main import create_app

CNPJ_ALFANUMERICO = "12.ABC.345/01DE-35"  # exemplo oficial da Receita Federal
WEB = {"X-Alessio-Client": "web"}

CLIENT = {
    "name": "Padaria Sol",
    "person_type": "pj",
    "document": CNPJ_ALFANUMERICO,
    "legal_name": "Padaria Sol Ltda",
    "email": "financeiro@padariasol.com.br",
    "phone": "(11) 3333-4444",
    "contact_name": "Marta Lima",
    "contact_email": "marta@padariasol.com.br",
    "contact_phone": "(11) 98888-7777",
    "address": {
        "postal_code": "01310-100",
        "street": "Av. Paulista",
        "street_number": "1000",
        "district": "Bela Vista",
        "city": "São Paulo",
        "state": "sp",
    },
}


@pytest.fixture
def created(staff_client):
    response = staff_client.post("/api/v1/platform/organizations", json=CLIENT)
    assert response.status_code == 201, response.text
    return response.json()


def base(created):
    return f"/api/v1/platform/organizations/{created['client']['id']}"


def test_client_registration_normalizes_and_invites_the_contact(staff_client, created):
    client = created["client"]
    assert client["document"] == "12ABC34501DE35"
    assert client["document_formatted"] == "12.ABC.345/01DE-35"
    assert client["phone"] == "1133334444"
    assert client["address"]["postal_code"] == "01310100"
    assert client["address"]["state"] == "SP"
    assert created["owner_email"] == "marta@padariasol.com.br"
    assert created["invite_token"]

    # Local principal criado com o endereço do cliente.
    [site] = staff_client.get(f"{base(created)}/sites").json()
    assert site["name"] == "Matriz" and site["address"]["city"] == "São Paulo"
    assert site["vision_planned"] is True

    # O responsável aceita o convite e entra como proprietário.
    with TestClient(create_app(), headers=WEB) as marta:
        accepted = marta.post(
            "/api/v1/auth/accept-invite",
            json={
                "token": created["invite_token"],
                "name": "Marta Lima",
                "password": "senha-da-marta-1",
            },
        )
        assert accepted.json()["role"] == "owner"


@pytest.mark.parametrize(
    "change, message",
    [
        ({"document": "12.ABC.345/01DE-36"}, "CNPJ inválido"),
        ({"person_type": "pf", "document": "529.982.247-24"}, "CPF inválido"),
        ({"phone": "1234"}, "telefone"),
        ({"address": {"postal_code": "123"}}, "CEP"),
        ({"address": {"state": "XX"}}, "UF"),
    ],
)
def test_client_data_is_validated(staff_client, change, message):
    response = staff_client.post("/api/v1/platform/organizations", json={**CLIENT, **change})
    assert response.status_code == 422
    assert message in response.text


def test_document_is_unique(staff_client, created):
    again = staff_client.post("/api/v1/platform/organizations", json={**CLIENT, "name": "Outra"})
    assert again.status_code == 409


def test_person_with_cpf_and_profile_edit(staff_client):
    pf = staff_client.post(
        "/api/v1/platform/organizations",
        json={
            **CLIENT,
            "person_type": "pf",
            "document": "529.982.247-25",
            "legal_name": "João Silva",
            "invite_contact": False,
        },
    ).json()
    assert pf["client"]["document_formatted"] == "529.982.247-25"
    assert pf["invite_token"] is None
    profile_url = f"/api/v1/platform/organizations/{pf['client']['id']}/profile"
    edited = staff_client.put(
        profile_url,
        json={
            **CLIENT,
            "person_type": "pf",
            "document": "52998224725",
            "legal_name": "João Silva",
            "status": "inactive",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "inactive"


def test_full_installation_in_one_step(staff_client, created):
    contract = staff_client.post(
        f"{base(created)}/contracts",
        json={
            "number": "PS-001",
            "starts_on": "2026-10-01",
            "signed_on": "2026-09-28",
            "term_months": 12,
            "auto_renew": True,
            "billing_day": 10,
            "payment_method": "boleto",
            "adjustment_index": "ipca",
        },
    ).json()[0]
    assert contract["billing_day"] == 10 and contract["payment_method"] == "boleto"
    [site] = staff_client.get(f"{base(created)}/sites").json()
    agent = staff_client.post(
        f"{base(created)}/agents", json={"name": "Mini PC loja", "site_id": site["id"]}
    ).json()
    assert agent["enrollment_code"]

    installed = staff_client.post(
        f"{base(created)}/cameras",
        json={
            "name": "Caixa",
            "site_id": site["id"],
            "vision": {
                "agent_id": agent["agent"]["id"],
                "source_ref": "caixa",
                "services": [
                    {
                        "service": "security",
                        "mode": "contract",
                        "contract_id": contract["id"],
                        "monthly_fee_cents": 12000,
                    },
                    {"service": "operation", "mode": "trial"},
                ],
            },
            "equipment": {
                "ownership": "comodato",
                "contract_id": contract["id"],
                "brand": "Intelbras",
                "model": "VIP 1230",
                "asset_tag": "ALV-0042",
                "monthly_fee_cents": 3000,
            },
        },
    )
    assert installed.status_code == 201, installed.text
    camera_id = installed.json()["camera_id"]

    services = staff_client.get(f"{base(created)}/services").json()
    [entry] = [c for c in services["cameras"] if c["camera_id"] == camera_id]
    assert entry["security"]["source"] == "contract"
    assert entry["operation"]["source"] == "trial"
    [equipment] = staff_client.get(f"{base(created)}/equipment").json()["items"]
    assert equipment["camera_id"] == camera_id and equipment["asset_tag"] == "ALV-0042"
    [org] = [
        o
        for o in staff_client.get("/api/v1/platform/organizations").json()
        if o["name"] == "Padaria Sol"
    ]
    assert org["total_monthly_cents"] == 15000

    # Agente ativado recebe a câmera com as duas modalidades.
    with TestClient(create_app()) as agent_client:
        token = agent_client.post(
            "/agent/v1/enroll", json={"code": agent["enrollment_code"], "agent_version": "0.3.0"}
        ).json()["token"]
        config = agent_client.get(
            "/agent/v1/config", headers={"Authorization": f"Bearer {token}"}
        ).json()
    [camera] = config["cameras"]
    assert camera["source_ref"] == "caixa"
    assert camera["services"] == ["operation", "security"]
    assert camera["rules"][0]["schedule"]["windows"][0]["start"] == "08:00:00"


def test_camera_without_vision_is_only_equipment(staff_client, created):
    site = staff_client.post(
        f"{base(created)}/sites", json={"name": "Depósito", "vision_planned": False}
    ).json()
    only_equipment = staff_client.post(
        f"{base(created)}/cameras",
        json={
            "name": "Portão",
            "site_id": site["id"],
            "equipment": {"ownership": "client", "brand": "Hikvision"},
        },
    )
    assert only_equipment.status_code == 201, only_equipment.text
    assert only_equipment.json()["camera_id"] is None
    assert staff_client.get(f"{base(created)}/cameras").json() == []

    # O local foi cadastrado sem Vision: a câmera não pode ter serviço.
    refused = staff_client.post(
        f"{base(created)}/cameras",
        json={
            "name": "Portão 2",
            "site_id": site["id"],
            "vision": {
                "agent_id": site["id"],
                "source_ref": "p2",
                "services": [{"service": "security", "mode": "trial"}],
            },
        },
    )
    assert refused.status_code == 422
    assert "sem serviço Vision" in refused.json()["detail"]


def test_failed_installation_saves_nothing(staff_client, created):
    [site] = staff_client.get(f"{base(created)}/sites").json()
    agent = staff_client.post(
        f"{base(created)}/agents", json={"name": "A", "site_id": site["id"]}
    ).json()
    vision = {
        "agent_id": agent["agent"]["id"],
        "source_ref": "cam1",
        "services": [{"service": "security", "mode": "trial"}],
    }
    first = staff_client.post(
        f"{base(created)}/cameras", json={"name": "Cam 1", "site_id": site["id"], "vision": vision}
    )
    assert first.status_code == 201
    duplicate = staff_client.post(
        f"{base(created)}/cameras",
        json={
            "name": "Cam 2",
            "site_id": site["id"],
            "vision": vision,
            "equipment": {"ownership": "client"},
        },
    )
    assert duplicate.status_code == 409
    assert staff_client.get(f"{base(created)}/equipment").json()["items"] == []
    assert len(staff_client.get(f"{base(created)}/cameras").json()) == 1


def test_only_staff_registers_clients(client):
    assert client.post("/api/v1/platform/organizations", json=CLIENT).status_code == 403
