from conftest import nueva_persona


def test_localidades_por_departamento(admin):
    r = admin.get("/api/localidades")
    assert r.status_code == 200
    d = r.json()
    assert "Monteros" in d["Monteros"] and "Aguilares" in d["Río Chico"] and "Tafí del Valle" in d["Tafí del Valle"]
    assert d["Capital"] == ["San Miguel de Tucumán"]
    # Una localidad nueva cargada en un legajo aparece sola en su departamento (sin duplicar las que ya están).
    nueva_persona(admin, localidad="Villa Ficticia", departamento="Simoca")
    nueva_persona(admin, apellidos="OTRO", nombres="Nombre", numero_documento="3000009", localidad="MONTEAGUDO", departamento="Simoca")
    d = admin.get("/api/localidades").json()
    assert "Villa Ficticia" in d["Simoca"] and d["Simoca"].count("Monteagudo") == 1 and "MONTEAGUDO" not in d["Simoca"]


def test_localidades_pide_sesion(cliente):
    from fastapi.testclient import TestClient
    from sulam.main import crear_app
    assert TestClient(crear_app()).get("/api/localidades").status_code == 401
