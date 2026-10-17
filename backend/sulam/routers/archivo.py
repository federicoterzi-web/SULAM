"""Archivo físico: dónde está cada carpeta en papel (legajo o expediente) y sus pases.

Pensado para que sea muy simple:
- **Pedir**: «necesito la carpeta». Quien la tiene (la persona o cualquiera de su área)
  la entrega y toca **Entregado**: la carpeta pasa a quien la pidió.
- **Pasar / devolver**: quien la tiene la envía a otra área o persona; quien la recibe
  toca **Recibido**.
- Si todavía no se sabe dónde está, cualquiera que la vea la registra.
Todo queda en el historial de la carpeta y en la auditoría.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..models import Area, Expediente, Pase, Persona, UbicacionFisica, Usuario
from ..permissions import Contexto
from ..schemas import Entrada
from ..security import ahora
from ..serializers import usuario_breve
from ._comun import no_encontrado

router = APIRouter(tags=["archivo"])


# ---------------------------------------------------------------- esquemas


class Objeto(Entrada):
    persona_id: uuid.UUID | None = None
    expediente_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _uno(self):
        if (self.persona_id is None) == (self.expediente_id is None):
            raise ValueError("Indique un legajo o un expediente.")
        return self


class UbicacionIn(Objeto):
    area_id: int
    usuario_id: uuid.UUID | None = None


class PedidoIn(Objeto):
    motivo: str | None = Field(default=None, max_length=1000)


class EnvioIn(Objeto):
    hacia_area_id: int
    hacia_usuario_id: uuid.UUID | None = None
    motivo: str | None = Field(default=None, max_length=1000)


class RespuestaIn(Entrada):
    respuesta: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------- auxiliares


def _filtro(persona_id, expediente_id):
    return (
        (UbicacionFisica.persona_id == persona_id) if persona_id else (UbicacionFisica.expediente_id == expediente_id)
    )


def _validar_objeto(db: Session, ctx: Contexto, o: Objeto) -> tuple[Persona | None, Expediente | None]:
    """Solo hace falta poder ver legajos (cualquier alcance) o ser parte del archivo."""
    if not (ctx.tiene("personas", "consultar") or ctx.tiene("expedientes", "consultar")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Su rol no permite consultar legajos.")
    if o.persona_id:
        p = db.get(Persona, o.persona_id)
        if p is None:
            raise no_encontrado("Legajo")
        return p, None
    e = db.get(Expediente, o.expediente_id)
    if e is None:
        raise no_encontrado("Expediente")
    return None, e


def _ubicacion(db: Session, persona_id=None, expediente_id=None) -> UbicacionFisica | None:
    return db.execute(select(UbicacionFisica).where(_filtro(persona_id, expediente_id))).scalar_one_or_none()


def _puede_actuar(ctx: Contexto, area_id: int | None, usuario_id: uuid.UUID | None) -> bool:
    """Quien tiene la carpeta, o cualquiera del área donde está."""
    return ctx.id == usuario_id or (area_id is not None and ctx.usuario.area_id == area_id)


def _pendiente(db: Session, persona_id=None, expediente_id=None) -> Pase | None:
    q = select(Pase).where(Pase.estado == "pendiente")
    q = q.where(Pase.persona_id == persona_id) if persona_id else q.where(Pase.expediente_id == expediente_id)
    return db.execute(q).scalars().first()


def _nombre_objeto(db: Session, persona_id, expediente_id) -> dict:
    if persona_id:
        p = db.get(Persona, persona_id)
        return {
            "tipo": "legajo",
            "persona_id": str(p.id),
            "texto": f"Legajo {p.numero_legajo} · {p.apellidos.upper()}, {p.nombres}",
        }
    e = db.get(Expediente, expediente_id)
    p = db.get(Persona, e.persona_id)
    return {
        "tipo": "expediente",
        "persona_id": str(p.id),
        "expediente_id": str(e.id),
        "texto": f"Expediente {e.numero} · {p.apellidos.upper()}, {p.nombres}",
    }


def _ubicacion_out(u: UbicacionFisica | None) -> dict | None:
    if u is None:
        return None
    return {
        "area": {"id": u.area.id, "nombre": u.area.nombre},
        "usuario": usuario_breve(u.usuario),
        "desde": u.desde.isoformat(),
    }


def _pase_out(db: Session, ctx: Contexto, p: Pase) -> dict:
    return {
        "id": p.id,
        "tipo": p.tipo,
        "objeto": _nombre_objeto(db, p.persona_id, p.expediente_id),
        "desde": {"area": p.desde_area.nombre if p.desde_area else None, "usuario": usuario_breve(p.desde_usuario)},
        "hacia": {"area": p.hacia_area.nombre, "usuario": usuario_breve(p.hacia_usuario)},
        "motivo": p.motivo,
        "estado": p.estado,
        "iniciado_por": usuario_breve(p.iniciador),
        "iniciado_en": p.iniciado_en.isoformat(),
        "resuelto_por": usuario_breve(p.resolvio),
        "resuelto_en": p.resuelto_en.isoformat() if p.resuelto_en else None,
        "respuesta": p.respuesta,
        "puedo_confirmar": p.estado == "pendiente" and _confirma(ctx, p),
        "puedo_cancelar": p.estado == "pendiente" and p.iniciado_por == ctx.id,
    }


def _confirma(ctx: Contexto, p: Pase) -> bool:
    if p.tipo == "pedido":  # entrega quien la tiene
        return _puede_actuar(ctx, p.desde_area_id, p.desde_usuario_id)
    return _puede_actuar(ctx, p.hacia_area_id, p.hacia_usuario_id)  # recibe el destino


def _mover(db: Session, ctx: Contexto, p: Pase) -> None:
    u = _ubicacion(db, p.persona_id, p.expediente_id)
    if u is None:
        u = UbicacionFisica(persona_id=p.persona_id, expediente_id=p.expediente_id, area_id=p.hacia_area_id)
        db.add(u)
    u.area_id = p.hacia_area_id
    u.usuario_id = p.hacia_usuario_id
    u.desde = ahora()
    u.actualizado_por = ctx.id


def _persona_de(db: Session, persona_id, expediente_id):
    if persona_id:
        return persona_id
    return db.get(Expediente, expediente_id).persona_id


# ---------------------------------------------------------------- consulta


@router.get("/archivo/ubicacion")
def ver_ubicacion(
    persona_id: uuid.UUID | None = None,
    expediente_id: uuid.UUID | None = None,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    o = Objeto(persona_id=persona_id, expediente_id=expediente_id)
    _validar_objeto(db, ctx, o)
    u = _ubicacion(db, persona_id, expediente_id)
    pend = _pendiente(db, persona_id, expediente_id)
    q = select(Pase).where(Pase.estado != "cancelado")
    q = q.where(Pase.persona_id == persona_id) if persona_id else q.where(Pase.expediente_id == expediente_id)
    historial = db.execute(q.order_by(Pase.iniciado_en.desc()).limit(15)).scalars().all()
    la_tengo = u is not None and (u.usuario_id == ctx.id or (u.usuario_id is None and u.area_id == ctx.usuario.area_id))
    return {
        "ubicacion": _ubicacion_out(u),
        "pendiente": _pase_out(db, ctx, pend) if pend else None,
        "historial": [_pase_out(db, ctx, p) for p in historial],
        "puedo": {
            "registrar": u is None or _puede_actuar(ctx, u.area_id, u.usuario_id) or ctx.tiene("personas", "administrar"),
            "pedir": u is not None and pend is None and not la_tengo and ctx.usuario.area_id is not None,
            "pasar": u is not None and pend is None and _puede_actuar(ctx, u.area_id, u.usuario_id),
        },
        "la_tengo": la_tengo,
    }


@router.put("/archivo/ubicacion")
def registrar_ubicacion(entrada: UbicacionIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Registrar (o corregir) dónde está la carpeta, sin pase."""
    _validar_objeto(db, ctx, entrada)
    if db.get(Area, entrada.area_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inexistente.")
    u = _ubicacion(db, entrada.persona_id, entrada.expediente_id)
    if u is not None and not (_puede_actuar(ctx, u.area_id, u.usuario_id) or ctx.tiene("personas", "administrar")):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Solo quien tiene la carpeta (o su área) puede corregir dónde está. Use «Pedir»."
        )
    if entrada.usuario_id is not None:
        usuario = db.get(Usuario, entrada.usuario_id)
        if usuario is None or not usuario.activo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Usuario inexistente.")
    antes = _ubicacion_out(u)
    if u is None:
        u = UbicacionFisica(persona_id=entrada.persona_id, expediente_id=entrada.expediente_id, area_id=entrada.area_id)
        db.add(u)
    u.area_id = entrada.area_id
    u.usuario_id = entrada.usuario_id
    u.desde = ahora()
    u.actualizado_por = ctx.id
    db.flush()
    db.refresh(u)
    audit.registrar(
        db, ctx, "registrar_ubicacion", "carpeta", entrada.persona_id or entrada.expediente_id,
        _persona_de(db, entrada.persona_id, entrada.expediente_id),
        {"antes": antes, "ahora": {"area": u.area.nombre, "usuario": u.usuario.usuario if u.usuario else None}},
    )
    db.commit()
    return ver_ubicacion(entrada.persona_id, entrada.expediente_id, ctx, db)


# ---------------------------------------------------------------- pases


@router.post("/archivo/pedidos", status_code=201)
def pedir(entrada: PedidoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _validar_objeto(db, ctx, entrada)
    if ctx.usuario.area_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Su usuario no tiene área: pida a Administración que la cargue.")
    u = _ubicacion(db, entrada.persona_id, entrada.expediente_id)
    if u is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Todavía no se registró dónde está la carpeta.")
    if u.usuario_id == ctx.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "La carpeta ya la tiene usted.")
    if _pendiente(db, entrada.persona_id, entrada.expediente_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay un pase pendiente de esta carpeta.")
    p = Pase(
        tipo="pedido",
        persona_id=entrada.persona_id,
        expediente_id=entrada.expediente_id,
        desde_area_id=u.area_id,
        desde_usuario_id=u.usuario_id,
        hacia_area_id=ctx.usuario.area_id,
        hacia_usuario_id=ctx.id,
        motivo=(entrada.motivo or "").strip() or None,
        iniciado_por=ctx.id,
    )
    db.add(p)
    db.flush()
    audit.registrar(db, ctx, "pedir_carpeta", "pase", p.id, _persona_de(db, p.persona_id, p.expediente_id), {"motivo": p.motivo})
    db.commit()
    db.refresh(p)
    return _pase_out(db, ctx, p)


@router.post("/archivo/envios", status_code=201)
def enviar(entrada: EnvioIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _validar_objeto(db, ctx, entrada)
    u = _ubicacion(db, entrada.persona_id, entrada.expediente_id)
    if u is None or not _puede_actuar(ctx, u.area_id, u.usuario_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo quien tiene la carpeta (o su área) puede pasarla.")
    if _pendiente(db, entrada.persona_id, entrada.expediente_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay un pase pendiente de esta carpeta.")
    if db.get(Area, entrada.hacia_area_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inexistente.")
    if entrada.hacia_usuario_id is not None:
        dest = db.get(Usuario, entrada.hacia_usuario_id)
        if dest is None or not dest.activo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Usuario inexistente.")
    if entrada.hacia_area_id == u.area_id and entrada.hacia_usuario_id == u.usuario_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La carpeta ya está ahí.")
    p = Pase(
        tipo="envio",
        persona_id=entrada.persona_id,
        expediente_id=entrada.expediente_id,
        desde_area_id=u.area_id,
        desde_usuario_id=u.usuario_id,
        hacia_area_id=entrada.hacia_area_id,
        hacia_usuario_id=entrada.hacia_usuario_id,
        motivo=(entrada.motivo or "").strip() or None,
        iniciado_por=ctx.id,
    )
    db.add(p)
    db.flush()
    audit.registrar(db, ctx, "enviar_carpeta", "pase", p.id, _persona_de(db, p.persona_id, p.expediente_id), {"hacia": p.hacia_area.nombre})
    db.commit()
    db.refresh(p)
    return _pase_out(db, ctx, p)


def _pase(db: Session, pase_id: int) -> Pase:
    p = db.get(Pase, pase_id)
    if p is None:
        raise no_encontrado("Pase")
    if p.estado != "pendiente":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese pase ya se resolvió.")
    return p


@router.post("/archivo/pases/{pase_id}/confirmar")
def confirmar(pase_id: int, entrada: RespuestaIn | None = None, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    p = _pase(db, pase_id)
    if not _confirma(ctx, p):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Lo confirma quien tiene la carpeta al entregarla." if p.tipo == "pedido" else "Lo confirma quien la recibe.",
        )
    p.estado = "hecho"
    p.resuelto_por = ctx.id
    p.resuelto_en = ahora()
    p.respuesta = (entrada.respuesta if entrada else None) or None
    _mover(db, ctx, p)
    audit.registrar(db, ctx, "entregar_carpeta" if p.tipo == "pedido" else "recibir_carpeta", "pase", p.id,
                    _persona_de(db, p.persona_id, p.expediente_id), {"hacia": p.hacia_area.nombre})
    db.commit()
    db.refresh(p)
    return _pase_out(db, ctx, p)


@router.post("/archivo/pases/{pase_id}/rechazar")
def rechazar(pase_id: int, entrada: RespuestaIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    p = _pase(db, pase_id)
    if not _confirma(ctx, p):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No le corresponde responder este pase.")
    if not (entrada.respuesta or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indique el motivo (p. ej., «la tiene otra persona»).")
    p.estado = "rechazado"
    p.resuelto_por = ctx.id
    p.resuelto_en = ahora()
    p.respuesta = entrada.respuesta.strip()
    audit.registrar(db, ctx, "rechazar_pase", "pase", p.id, _persona_de(db, p.persona_id, p.expediente_id), {"respuesta": p.respuesta})
    db.commit()
    db.refresh(p)
    return _pase_out(db, ctx, p)


@router.post("/archivo/pases/{pase_id}/cancelar")
def cancelar(pase_id: int, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    p = _pase(db, pase_id)
    if p.iniciado_por != ctx.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo quien lo inició puede cancelarlo.")
    p.estado = "cancelado"
    p.resuelto_por = ctx.id
    p.resuelto_en = ahora()
    audit.registrar(db, ctx, "cancelar_pase", "pase", p.id, _persona_de(db, p.persona_id, p.expediente_id))
    db.commit()
    db.refresh(p)
    return _pase_out(db, ctx, p)


# ---------------------------------------------------------------- bandeja


def _para_mi(db: Session, ctx: Contexto) -> tuple[list[Pase], list[Pase]]:
    pendientes = db.execute(select(Pase).where(Pase.estado == "pendiente").order_by(Pase.iniciado_en)).scalars().all()
    entregar = [p for p in pendientes if p.tipo == "pedido" and _confirma(ctx, p)]
    recibir = [p for p in pendientes if p.tipo == "envio" and _confirma(ctx, p)]
    return entregar, recibir


@router.get("/archivo/pendientes")
def pendientes(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    entregar, recibir = _para_mi(db, ctx)
    return {"entregar": len(entregar), "recibir": len(recibir), "cantidad": len(entregar) + len(recibir)}


@router.get("/archivo/bandeja")
def bandeja(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    entregar, recibir = _para_mi(db, ctx)
    mios = db.execute(
        select(Pase).where(Pase.estado == "pendiente", Pase.iniciado_por == ctx.id).order_by(Pase.iniciado_en.desc())
    ).scalars().all()
    recientes = db.execute(
        select(Pase)
        .where(Pase.estado.in_(("hecho", "rechazado")), or_(Pase.iniciado_por == ctx.id, Pase.resuelto_por == ctx.id))
        .order_by(Pase.resuelto_en.desc())
        .limit(10)
    ).scalars().all()
    en_poder = db.execute(
        select(UbicacionFisica).where(UbicacionFisica.usuario_id == ctx.id).order_by(UbicacionFisica.desde)
    ).scalars().all()
    return {
        "entregar": [_pase_out(db, ctx, p) for p in entregar],
        "recibir": [_pase_out(db, ctx, p) for p in recibir],
        "mis_pedidos": [_pase_out(db, ctx, p) for p in mios],
        "recientes": [_pase_out(db, ctx, p) for p in recientes],
        "en_mi_poder": [
            {**_nombre_objeto(db, u.persona_id, u.expediente_id), "desde": u.desde.isoformat()} for u in en_poder
        ],
        "area_registro": db.execute(select(Area.id).where(Area.nombre == "Oficina de Registro")).scalar(),
    }


class CargaInicialIn(Entrada):
    numeros: list[str] = Field(min_length=1, max_length=2000)


@router.post("/archivo/carga-inicial")
def carga_inicial(entrada: CargaInicialIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Registro anota de una vez las carpetas que tiene, por número de legajo.
    Solo se cargan las que todavía no tienen ubicación (las demás se informan)."""
    area_id = ctx.usuario.area_id
    if area_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Su usuario no tiene área.")
    numeros = list(dict.fromkeys(n.strip().replace(".", "") for n in entrada.numeros if n.strip()))
    cargadas, ya_ubicadas, no_encontradas = [], [], []
    for numero in numeros:
        p = db.execute(select(Persona).where(Persona.numero_legajo == numero, Persona.unificada_en_id.is_(None))).scalar_one_or_none()
        if p is None:
            no_encontradas.append(numero)
            continue
        u = _ubicacion(db, persona_id=p.id)
        if u is not None:
            ya_ubicadas.append({"numero": numero, "donde": dondeesta_texto(u)})
            continue
        db.add(UbicacionFisica(persona_id=p.id, area_id=area_id, actualizado_por=ctx.id))
        cargadas.append(numero)
    if cargadas:
        audit.registrar(db, ctx, "carga_inicial_carpetas", "carpeta", None, None, {"area_id": area_id, "legajos": cargadas})
    db.commit()
    return {"cargadas": cargadas, "ya_ubicadas": ya_ubicadas, "no_encontradas": no_encontradas}


def dondeesta_texto(u: UbicacionFisica) -> str:
    return f"la tiene {u.usuario.nombre_completo}" if u.usuario else f"en {u.area.nombre}"
