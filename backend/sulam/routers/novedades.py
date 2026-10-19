"""Novedades: circulares e información de la Dirección (para todos) y de cada área.

- Ven: las generales y las de su área. Quien publica con alcance «todos» ve todas.
- Se pueden dirigir además a uno o más roles: entonces solo las reciben (y ven) quienes
  tienen alguno de esos roles, dentro de toda la Dirección o del área elegida.
- Publican (módulo «novedades», acción «publicar»): con alcance «todos», para toda
  la Dirección o cualquier área; con «área», solo para la propia.
- Confirmación de lectura: cada destinatario confirma una vez; quien gestiona la
  novedad ve quién confirmó y quién falta.
"""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import contexto
from ..informes import limpiar_html, texto_plano
from ..models import Area, Novedad, NovedadLectura, NovedadRol, Rol, Usuario, UsuarioRol
from ..permissions import Contexto
from ..security import ahora
from ..serializers import usuario_breve
from ..storage import almacenamiento_actual, almacenamiento_por_nombre, copiar_a_temporal, detectar_mime
from ._comun import no_encontrado

router = APIRouter(tags=["novedades"])


def _alcance(ctx: Contexto) -> str | None:
    return ctx.alcance("novedades", "publicar")


def _puede_gestionar(ctx: Contexto, n: Novedad) -> bool:
    alc = _alcance(ctx)
    if alc == "todos":
        return True
    if alc == "area":
        return n.area_id is not None and n.area_id == ctx.usuario.area_id
    return n.autor_id == ctx.id and alc is not None


def _mis_roles(ctx: Contexto) -> list[int]:
    return [r.id for r in ctx.usuario.roles]


def _visibles(ctx: Contexto):
    q = select(Novedad).where(Novedad.retirada_en.is_(None))
    if _alcance(ctx) == "todos":
        return q
    area = [Novedad.area_id.is_(None)]
    if ctx.usuario.area_id is not None:
        area.append(Novedad.area_id == ctx.usuario.area_id)
    # Con roles elegidos, solo la ven quienes tienen alguno de ellos (y quien la publicó).
    sin_roles = ~exists().where(NovedadRol.novedad_id == Novedad.id)
    con_mi_rol = exists().where(NovedadRol.novedad_id == Novedad.id, NovedadRol.rol_id.in_(_mis_roles(ctx) or [-1]))
    return q.where(or_(Novedad.autor_id == ctx.id, and_(or_(*area), or_(sin_roles, con_mi_rol))))


def _es_destinatario(ctx: Contexto, n: Novedad) -> bool:
    if n.autor_id == ctx.id:
        return False
    if n.area_id is not None and n.area_id != ctx.usuario.area_id:
        return False
    return not n.roles or bool({r.id for r in n.roles} & set(_mis_roles(ctx)))


def _destinatarios(db: Session, n: Novedad) -> list[Usuario]:
    q = select(Usuario).where(Usuario.activo.is_(True))
    if n.area_id is not None:
        q = q.where(Usuario.area_id == n.area_id)
    if n.roles:
        q = q.where(Usuario.id.in_(select(UsuarioRol.usuario_id).where(UsuarioRol.rol_id.in_([r.id for r in n.roles]))))
    if n.autor_id is not None:
        q = q.where(Usuario.id != n.autor_id)
    return list(db.execute(q.order_by(Usuario.nombre_completo)).scalars())


def _obtener(db: Session, ctx: Contexto, novedad_id: uuid.UUID) -> Novedad:
    n = db.get(Novedad, novedad_id)
    if n is None or n.retirada_en is not None:
        raise no_encontrado("Novedad")
    visible = db.execute(_visibles(ctx).where(Novedad.id == n.id)).scalar_one_or_none()
    if visible is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esa novedad es de otra área.")
    return n


def _out(db: Session, ctx: Contexto, n: Novedad, mias: dict) -> dict:
    gestiona = _puede_gestionar(ctx, n)
    r = {
        "id": str(n.id),
        "titulo": n.titulo,
        "cuerpo": n.cuerpo,
        "area": {"id": n.area.id, "nombre": n.area.nombre} if n.area else None,
        "roles": [{"id": r.id, "nombre": r.nombre} for r in sorted(n.roles, key=lambda r: r.nombre)],
        "requiere_confirmacion": n.requiere_confirmacion,
        "fijada": n.fijada,
        "archivo": (
            {"nombre": n.archivo_nombre, "mime": n.archivo_mime, "tamano": n.archivo_tamano} if n.archivo_clave else None
        ),
        "autor": usuario_breve(n.autor),
        "publicada_en": n.publicada_en.isoformat(),
        "es_destinatario": _es_destinatario(ctx, n),
        "confirmada_en": mias[n.id].isoformat() if n.id in mias else None,
        "puede_gestionar": gestiona,
    }
    if gestiona and n.requiere_confirmacion:
        dest = _destinatarios(db, n)
        ids = {u.id for u in dest}
        confirmaron = db.execute(
            select(func.count()).select_from(NovedadLectura).where(
                NovedadLectura.novedad_id == n.id, NovedadLectura.usuario_id.in_(ids)
            )
        ).scalar_one()
        r["lecturas"] = {"destinatarios": len(dest), "confirmaron": confirmaron}
    return r


def _mis_confirmaciones(db: Session, ctx: Contexto) -> dict:
    return dict(
        db.execute(
            select(NovedadLectura.novedad_id, NovedadLectura.confirmada_en).where(NovedadLectura.usuario_id == ctx.id)
        ).all()
    )


@router.get("/novedades")
def listar(
    filtro: str = Query("todas", pattern="^(todas|direccion|area|pendientes)$"),
    limite: int = Query(100, ge=1, le=300),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    q = _visibles(ctx)
    if filtro == "direccion":
        q = q.where(Novedad.area_id.is_(None))
    elif filtro == "area":
        q = q.where(Novedad.area_id.is_not(None))
    mias = _mis_confirmaciones(db, ctx)
    lista = list(db.execute(q.order_by(Novedad.fijada.desc(), Novedad.publicada_en.desc()).limit(limite)).scalars())
    if filtro == "pendientes":
        lista = [n for n in lista if n.requiere_confirmacion and _es_destinatario(ctx, n) and n.id not in mias]
    alc = _alcance(ctx)
    areas_publicables = []
    if alc == "todos":
        areas_publicables = [{"id": None, "nombre": "Toda la Dirección"}] + [
            {"id": a.id, "nombre": a.nombre} for a in db.execute(select(Area).where(Area.activo).order_by(Area.nombre)).scalars()
        ]
    elif alc == "area" and ctx.usuario.area_id:
        a = db.get(Area, ctx.usuario.area_id)
        areas_publicables = [{"id": a.id, "nombre": a.nombre}]
    return {
        "novedades": [_out(db, ctx, n, mias) for n in lista],
        "puede_publicar": bool(areas_publicables),
        "areas_publicables": areas_publicables,
        "roles_publicables": (
            [{"id": r.id, "nombre": r.nombre} for r in db.execute(select(Rol).where(Rol.activo).order_by(Rol.nombre)).scalars()]
            if areas_publicables
            else []
        ),
    }


@router.get("/novedades/pendientes")
def pendientes(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Novedades que la persona todavía no confirmó (para el inicio y el menú)."""
    mias = _mis_confirmaciones(db, ctx)
    lista = [
        n
        for n in db.execute(_visibles(ctx).where(Novedad.requiere_confirmacion).order_by(Novedad.publicada_en.desc())).scalars()
        if _es_destinatario(ctx, n) and n.id not in mias
    ]
    return {
        "cantidad": len(lista),
        "novedades": [
            {
                "id": str(n.id),
                "titulo": n.titulo,
                "area": n.area.nombre if n.area else None,
                "autor": n.autor.nombre_completo if n.autor else None,
                "publicada_en": n.publicada_en.isoformat(),
                "resumen": texto_plano(n.cuerpo)[:220],
                "archivo": bool(n.archivo_clave),
            }
            for n in lista[:5]
        ],
    }


MAX_ARCHIVO = 15 * 1024 * 1024


@router.post("/novedades", status_code=201)
def publicar(
    titulo: str = Form(..., min_length=3, max_length=300),
    cuerpo: str = Form("", max_length=100_000),
    area_id: str | None = Form(None),
    roles_ids: str | None = Form(None),
    requiere_confirmacion: bool = Form(True),
    fijada: bool = Form(False),
    archivo: UploadFile | None = File(None),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    alc = ctx.requerir("novedades", "publicar")
    aid = int(area_id) if area_id and area_id.strip() else None
    if aid is not None and db.get(Area, aid) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inexistente.")
    if alc != "todos":
        if aid is None or aid != ctx.usuario.area_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Solo puede publicar para su área. Las novedades para todos las publica la Dirección."
            )
    roles: list[Rol] = []
    if roles_ids and roles_ids.strip():
        try:
            pedidos = {int(x) for x in roles_ids.split(",") if x.strip()}
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roles inválidos.")
        roles = list(db.execute(select(Rol).where(Rol.id.in_(pedidos), Rol.activo)).scalars())
        if len(roles) != len(pedidos):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hay roles inexistentes o dados de baja.")
    html = limpiar_html(cuerpo)
    if not texto_plano(html).strip() and archivo is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escriba el texto de la novedad o adjunte la circular.")
    n = Novedad(
        titulo=titulo.strip(),
        cuerpo=html,
        area_id=aid,
        requiere_confirmacion=requiere_confirmacion,
        fijada=fijada,
        autor_id=ctx.id,
    )
    n.roles = roles
    if archivo is not None and archivo.filename:
        cfg = get_settings()
        cabecera = archivo.file.read(16)
        archivo.file.seek(0)
        mime = detectar_mime(cabecera)
        if mime is None or mime not in cfg.allowed_mime:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "La circular debe ser PDF, JPG o PNG.")
        try:
            tmp, _ = copiar_a_temporal(archivo.file, MAX_ARCHIVO)
        except ValueError:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "El archivo supera los 15 MB.")
        almacen = almacenamiento_actual()
        with tmp:
            g = almacen.guardar(tmp)
        n.archivo_nombre = (archivo.filename or "circular")[:300]
        n.archivo_mime = mime
        n.archivo_tamano = g.tamano
        n.archivo_sha256 = g.sha256
        n.archivo_almacenamiento = almacen.nombre
        n.archivo_clave = g.clave
    db.add(n)
    db.flush()
    audit.registrar(
        db, ctx, "publicar", "novedad", n.id, None,
        {
            "titulo": n.titulo,
            "area_id": aid,
            "roles": [r.nombre for r in roles],
            "archivo": n.archivo_nombre,
            "requiere_confirmacion": requiere_confirmacion,
        },
    )
    db.commit()
    db.refresh(n)
    return _out(db, ctx, n, {})


@router.post("/novedades/{novedad_id}/confirmar")
def confirmar(novedad_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    n = _obtener(db, ctx, novedad_id)
    ya = db.get(NovedadLectura, (n.id, ctx.id))
    if ya is None:
        ya = NovedadLectura(novedad_id=n.id, usuario_id=ctx.id, confirmada_en=ahora())
        db.add(ya)
        audit.registrar(db, ctx, "confirmar_lectura", "novedad", n.id, None, {"titulo": n.titulo})
        db.commit()
    return {"confirmada_en": ya.confirmada_en.isoformat()}


@router.get("/novedades/{novedad_id}/lecturas")
def lecturas(novedad_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    n = _obtener(db, ctx, novedad_id)
    if not _puede_gestionar(ctx, n):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo quien publica en esa área ve las confirmaciones.")
    confirmadas = dict(
        db.execute(select(NovedadLectura.usuario_id, NovedadLectura.confirmada_en).where(NovedadLectura.novedad_id == n.id)).all()
    )
    dest = _destinatarios(db, n)
    def fila(u: Usuario) -> dict:
        return {"usuario": usuario_breve(u), "area": u.area.nombre if u.area else None, "confirmada_en": confirmadas[u.id].isoformat() if u.id in confirmadas else None}
    return {
        "confirmaron": [fila(u) for u in dest if u.id in confirmadas],
        "faltan": [fila(u) for u in dest if u.id not in confirmadas],
    }


@router.get("/novedades/{novedad_id}/archivo")
def archivo(novedad_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    n = _obtener(db, ctx, novedad_id)
    if not n.archivo_clave:
        raise no_encontrado("Archivo")
    almacen = almacenamiento_por_nombre(n.archivo_almacenamiento)
    f = almacen.abrir(n.archivo_clave)

    def iterar():
        with f:
            while bloque := f.read(256 * 1024):
                yield bloque

    return StreamingResponse(
        iterar(),
        media_type=n.archivo_mime,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(n.archivo_nombre or 'circular')}",
            "Content-Length": str(n.archivo_tamano),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/novedades/{novedad_id}/retirar")
def retirar(novedad_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    n = _obtener(db, ctx, novedad_id)
    if not _puede_gestionar(ctx, n):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puede retirar esta novedad.")
    n.retirada_en = ahora()
    n.retirada_por = ctx.id
    audit.registrar(db, ctx, "retirar", "novedad", n.id, None, {"titulo": n.titulo})
    db.commit()
    return {"ok": True}
