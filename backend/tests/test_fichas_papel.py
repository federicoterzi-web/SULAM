"""Fichas en papel: generación y lectura automática con fotos simuladas.

Se dibujan marcas y números "a mano" sobre la ficha, se deforma la imagen como
lo haría una foto con el celular (perspectiva, giro, sombra, ruido, desenfoque)
y se verifica que el lector recupere exactamente lo marcado.
"""

from __future__ import annotations

import random

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pdfium = pytest.importorskip("pypdfium2")

from sulam.papel.fichas import FICHAS, ficha  # noqa: E402
from sulam.papel.lectura import PX_MM, ErrorLectura, leer  # noqa: E402


def _render(codigo: str, pagina: int, ppmm: float = 8.0) -> np.ndarray:
    pdf, _ = ficha(codigo)
    doc = pdfium.PdfDocument(pdf)
    img = doc[pagina - 1].render(scale=ppmm * 25.4 / 72).to_pil().convert("L")
    return np.array(img)


def _x_a_mano(img, e, ppmm, rng):
    """Una X trazada con birome, algo torcida y no siempre centrada."""
    x0, y0 = e["x"] * ppmm, e["y"] * ppmm
    w, h = e["w"] * ppmm, e["h"] * ppmm
    j = lambda: rng.uniform(-0.12, 0.12) * w  # noqa: E731
    grosor = max(2, int(ppmm * 0.35))
    p = lambda fx, fy: (int(x0 + fx * w + j()), int(y0 + fy * h + j()))  # noqa: E731
    cv2.line(img, p(0.15, 0.15), p(0.85, 0.85), 30, grosor, cv2.LINE_AA)
    cv2.line(img, p(0.85, 0.15), p(0.15, 0.85), 30, grosor, cv2.LINE_AA)


def _digito(img, celda, d, ppmm):
    x = int((celda["x"] + 1.2) * ppmm)
    y = int((celda["y"] + celda["h"] - 1.4) * ppmm)
    cv2.putText(img, str(d), (x, y), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, ppmm * 0.16, 40, max(2, int(ppmm * 0.3)), cv2.LINE_AA)


def _como_foto(hoja, rng, giro=0):
    """Simula una foto: fondo, perspectiva, rotación, sombra, ruido y desenfoque."""
    h, w = hoja.shape
    lienzo = np.full((int(h * 1.35), int(w * 1.35)), rng.randint(90, 160), np.uint8)
    ox, oy = (lienzo.shape[1] - w) // 2, (lienzo.shape[0] - h) // 2
    origen = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    d = lambda: rng.uniform(-0.06, 0.06) * w  # noqa: E731
    destino = np.float32([[ox + d(), oy + d()], [ox + w + d(), oy + d()], [ox + w + d(), oy + h + d()], [ox + d(), oy + h + d()]])
    m = cv2.getPerspectiveTransform(origen, destino)
    foto = cv2.warpPerspective(hoja, m, (lienzo.shape[1], lienzo.shape[0]), dst=lienzo, borderMode=cv2.BORDER_TRANSPARENT)
    # sombra en diagonal
    gy, gx = np.mgrid[0:foto.shape[0], 0:foto.shape[1]]
    sombra = 1.0 - 0.35 * (gx / foto.shape[1]) * (gy / foto.shape[0])
    foto = (foto.astype(np.float32) * sombra).clip(0, 255)
    foto = foto + np.random.default_rng(rng.randint(0, 999)).normal(0, 6, foto.shape)
    foto = cv2.GaussianBlur(foto.clip(0, 255).astype(np.uint8), (3, 3), 0)
    if giro:
        foto = np.ascontiguousarray(np.rot90(foto, giro))
    # el celular reduce la imagen a ~12 MP
    return cv2.resize(foto, None, fx=0.85, fy=0.85, interpolation=cv2.INTER_AREA)


def test_fichas_entran_en_la_hoja_y_tienen_plantilla():
    for codigo in FICHAS:
        pdf, plantilla = ficha(codigo)
        assert pdf.startswith(b"%PDF")
        for p in plantilla["paginas"]:
            ids = [e["id"] for e in p["elementos"]]
            assert len(ids) == len(set(ids)), f"Ids repetidos en {codigo} hoja {p['pagina']}"
            for e in p["elementos"]:
                assert 15 <= e["x"] and e["x"] + e["w"] <= 195 and 14 <= e["y"] and e["y"] + e["h"] <= 282


@pytest.mark.parametrize("codigo,pagina,giro,semilla", [
    ("CAR", 1, 0, 1), ("CAR", 1, 2, 2), ("RDD", 1, 0, 3), ("RDD", 2, 1, 4), ("EVO", 1, 3, 5),
])
def test_lectura_de_casillas_en_foto_simulada(codigo, pagina, giro, semilla):
    rng = random.Random(semilla)
    ppmm = 8.0
    hoja = _render(codigo, pagina, ppmm)
    _, plantilla = ficha(codigo)
    elementos = plantilla["paginas"][pagina - 1]["elementos"]

    casillas = [e for e in elementos if e["tipo"] == "casilla"]
    marcadas = {e["id"] for e in rng.sample(casillas, k=min(len(casillas), 9))} if casillas else set()
    for e in casillas:
        if e["id"] in marcadas:
            _x_a_mano(hoja, e, ppmm, rng)
    numeros = {}
    for e in elementos:
        if e["tipo"] == "digitos" and e["campo"] in ("numero_actuacion", "numero_legajo", "fecha_ingreso"):
            numeros[e["id"]] = [rng.randint(0, 9) for _ in e["celdas"]]
            for celda, d in zip(e["celdas"], numeros[e["id"]]):
                _digito(hoja, celda, d, ppmm)

    res = leer(_como_foto(hoja, rng, giro))
    assert (res.ficha, res.pagina) == (codigo, pagina)
    detectadas = {i for i, c in res.casillas.items() if c["marcada"]}
    assert detectadas == marcadas
    assert not any(c["dudosa"] for i, c in res.casillas.items() if i not in marcadas and not c["unica"])
    for id_ in numeros:
        assert not res.campos[id_]["vacio"]
        assert all(not c["vacia"] for c in res.campos[id_]["celdas"])
    vacios = [e["id"] for e in elementos if e["tipo"] == "digitos" and e["id"] not in numeros]
    assert all(res.campos[i]["vacio"] for i in vacios)
    assert res.imagen.shape == (int(297 * PX_MM), int(210 * PX_MM))


def test_imagen_sin_ficha():
    with pytest.raises(ErrorLectura):
        leer(np.full((1200, 900), 200, np.uint8))


def test_descarga_de_fichas_en_blanco(admin):
    lista = admin.get("/api/formularios/papel").json()
    assert {f["codigo"] for f in lista} == {"CAR", "RDD", "EVO"}
    r = admin.get("/api/formularios/papel/car.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert admin.get("/api/formularios/papel/XYZ.pdf").status_code == 404
