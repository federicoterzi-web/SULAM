"""Administración: usuarios, roles, permisos y catálogos."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..models import Area, Caso, Rol, RolPermiso, TipoDocumental, TipoVinculo, Usuario
from ..permissions import ALCANCES, CATALOGO, DESCRIPCION_ACCIONES, Contexto, permiso_valido, permisos_efectivos
from ..numbering import fijar_proximo, proximo
from ..schemas import CatalogoIn, NumeracionIn, ResetPasswordIn, RolIn, UsuarioIn, UsuarioPatch
from ..security import hash_password, revocar_sesiones_usuario, validar_password_nueva

router = APIRouter(prefix="/admin", tags=["administración"])


def _admin(ctx: Contexto = Depends(contexto)) -> Contexto:
    ctx.requerir("administracion", "administrar")
    return ctx


def _rol_out(r: Rol) -> dict:
    return {
        "id": r.id,
        "nombre": r.nombre,
        "descripcion": r.descripcion,
        "activo": r.activo,
        "inicio": r.inicio,
        "permisos": [
            {"modulo": p.modulo, "accion": p.accion, "alcance": p.alcance}
            for p in sorted(r.permisos, key=lambda p: (p.modulo, p.accion))
        ],
    }


def _usuario_out(u: Usuario) -> dict:
    return {
        "id": str(u.id),
        "usuario": u.usuario,
        "nombre_completo": u.nombre_completo,
        "email": u.email,
        "area": {"id": u.area.id, "nombre": u.area.nombre} if u.area else None,
        "roles": [{"id": r.id, "nombre": r.nombre} for r in u.roles],
        "activo": u.activo,
        "debe_cambiar_password": u.debe_cambiar_password,
        "ultimo_acceso": u.ultimo_acceso.isoformat() if u.ultimo_acceso else None,
        "bloqueado_hasta": u.bloqueado_hasta.isoformat() if u.bloqueado_hasta else None,
    }


def _queda_un_administrador(db: Session) -> None:
    """Impide dejar el sistema sin ningún usuario activo capaz de administrarlo."""
    db.flush()
    for u in db.execute(select(Usuario).where(Usuario.activo)).scalars():
        db.refresh(u)
        if ("administracion", "administrar") in permisos_efectivos(u):
            return
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        "El cambio dejaría al sistema sin ningún usuario administrador activo.",
    )


# ---------------------------------------------------------------- permisos y roles


@router.get("/permisos-catalogo")
def catalogo_permisos(ctx: Contexto = Depends(_admin)):
    return {
        "modulos": [
            {"modulo": m, "nombre": d["nombre"], "acciones": d["acciones"]} for m, d in CATALOGO.items()
        ],
        "acciones": DESCRIPCION_ACCIONES,
        "alcances": list(ALCANCES),
    }


@router.get("/inicios")
def inicios_disponibles(ctx: Contexto = Depends(_admin)):
    from .inicio import PERFILES

    return [{"codigo": k, "nombre": v} for k, v in PERFILES.items()]


@router.get("/roles")
def listar_roles(ctx: Contexto = Depends(_admin), db: Session = Depends(get_db)):
    return [_rol_out(r) for r in db.execute(select(Rol).order_by(Rol.nombre)).scalars()]


def _aplicar_rol(db: Session, rol: Rol, datos: RolIn) -> None:
    vistos = set()
    for p in datos.permisos:
        if not permiso_valido(p.modulo, p.accion, p.alcance):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Permiso inválido: {p.modulo}.{p.accion}")
        if (p.modulo, p.accion) in vistos:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Permiso repetido: {p.modulo}.{p.accion}")
        vistos.add((p.modulo, p.accion))
    rol.nombre = datos.nombre
    rol.descripcion = datos.descripcion
    rol.activo = datos.activo
    if "inicio" in datos.model_fields_set:
        rol.inicio = datos.inicio
    rol.permisos.clear()
    db.flush()
    for p in datos.permisos:
        rol.permisos.append(RolPermiso(modulo=p.modulo, accion=p.accion, alcance=p.alcance))


@router.post("/roles", status_code=201)
def crear_rol(datos: RolIn, ctx: Contexto = Depends(_admin), db: Session = Depends(get_db)):
    rol = Rol()
    db.add(rol)
    _aplicar_rol(db, rol, datos)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un rol con ese nombre.")
    audit.registrar(db, ctx, "crear", "rol", rol.id, detalle=_rol_out(rol))
    db.commit()
    return _rol_out(rol)


@router.put("/roles/{rol_id}")
def reemplazar_rol(rol_id: int, datos: RolIn, ctx: Contexto = Depends(_admin), db: Session = Depends(get_db)):
    rol = db.get(Rol, rol_id)
    if rol is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rol inexistente.")
    antes = _rol_out(rol)
    _aplicar_rol(db, rol, datos)
    try:
        _queda_un_administrador(db)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un rol con ese nombre.")
    audit.registrar(db, ctx, "modificar_permisos", "rol", rol.id, detalle={"antes": antes, "despues": _rol_out(rol)})
    db.commit()
    return _rol_out(rol)


# ---------------------------------------------------------------- usuarios


@router.get("/usuarios")
def listar_usuarios(ctx: Contexto = Depends(_admin), db: Session = Depends(get_db)):
    return [_usuario_out(u) for u in db.execute(select(Usuario).order_by(Usuario.nombre_completo)).scalars()]


def _roles(db: Session, ids: list[int]) -> list[Rol]:
    roles = list(db.execute(select(Rol).where(Rol.id.in_(ids))).scalars())
    if len(roles) != len(set(ids)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Algún rol indicado no existe.")
    return roles


def _validar_area(db: Session, area_id: int | None) -> None:
    if area_id is not None and db.get(Area, area_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inválida.")


@router.post("/usuarios", status_code=201)
def crear_usuario(datos: UsuarioIn, ctx: Contexto = Depends(_admin), db: Session = Depends(get_db)):
    error = validar_password_nueva(datos.password_inicial)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
    existe = db.execute(
        select(Usuario.id).where(func.lower(Usuario.usuario) == datos.usuario.lower())
    ).first()
    if existe:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese nombre de usuario ya existe.")
    _validar_area(db, datos.area_id)
    u = Usuario(
        usuario=datos.usuario.lower(),
        nombre_completo=datos.nombre_completo,
        email=datos.email,
        area_id=datos.area_id,
        password_hash=hash_password(datos.password_inicial),
        debe_cambiar_password=True,
    )
    u.roles = _roles(db, datos.roles)
    db.add(u)
    db.flush()
    db.refresh(u)
    audit.registrar(
        db, ctx, "crear", "usuario", u.id,
        detalle={"usuario": u.usuario, "roles": [r.nombre for r in u.roles], "area_id": u.area_id},
    )
    db.commit()
    return _usuario_out(u)


@router.patch("/usuarios/{usuario_id}")
def modificar_usuario(
    usuario_id: uuid.UUID, datos: UsuarioPatch, ctx: Contexto = Depends(_admin), db: Session = Depends(get_db)
):
    u = db.get(Usuario, usuario_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario inexistente.")
    cambios_pedidos = datos.model_dump(exclude_unset=True)
    roles_nuevos = cambios_pedidos.pop("roles", None)
    if "area_id" in cambios_pedidos:
        _validar_area(db, cambios_pedidos["area_id"])
    diff = audit.cambios(u, cambios_pedidos)
    if roles_nuevos is not None:
        antes = sorted(r.nombre for r in u.roles)
        u.roles = _roles(db, roles_nuevos)
        despues = sorted(r.nombre for r in u.roles)
        if antes != despues:
            diff["roles"] = [antes, despues]
    if diff:
        try:
            _queda_un_administrador(db)
        except HTTPException:
            db.rollback()
            raise
        if cambios_pedidos.get("activo") is False:
            revocar_sesiones_usuario(db, u.id)
        audit.registrar(db, ctx, "modificar", "usuario", u.id, detalle={"cambios": diff})
        db.commit()
        db.refresh(u)
    return _usuario_out(u)


@router.post("/usuarios/{usuario_id}/password")
def restablecer_password(
    usuario_id: uuid.UUID, datos: ResetPasswordIn, ctx: Contexto = Depends(_admin), db: Session = Depends(get_db)
):
    u = db.get(Usuario, usuario_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario inexistente.")
    error = validar_password_nueva(datos.password_temporal)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
    u.password_hash = hash_password(datos.password_temporal)
    u.debe_cambiar_password = True
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    revocar_sesiones_usuario(db, u.id)
    audit.registrar(db, ctx, "restablecer_password", "usuario", u.id)
    db.commit()
    return _usuario_out(u)


# ---------------------------------------------------------------- catálogos

_CATALOGOS = {
    "areas": (Area, "area"),
    "tipos-documentales": (TipoDocumental, "tipo_documental"),
    "tipos-vinculo": (TipoVinculo, "tipo_vinculo"),
}


def _catalogo_out(obj) -> dict:
    return {"id": obj.id, "nombre": obj.nombre, "activo": obj.activo}


def _modelo(catalogo: str):
    if catalogo not in _CATALOGOS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catálogo inexistente.")
    return _CATALOGOS[catalogo]


@router.get("/catalogos/{catalogo}")
def listar_catalogo(catalogo: str, ctx: Contexto = Depends(_admin), db: Session = Depends(get_db)):
    modelo, _ = _modelo(catalogo)
    return [_catalogo_out(o) for o in db.execute(select(modelo).order_by(modelo.nombre)).scalars()]


@router.post("/catalogos/{catalogo}", status_code=201)
def crear_item(catalogo: str, datos: CatalogoIn, ctx: Contexto = Depends(_admin), db: Session = Depends(get_db)):
    modelo, entidad = _modelo(catalogo)
    obj = modelo(nombre=datos.nombre, activo=datos.activo)
    db.add(obj)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un elemento con ese nombre.")
    audit.registrar(db, ctx, "crear", entidad, obj.id, detalle=_catalogo_out(obj))
    db.commit()
    return _catalogo_out(obj)


@router.patch("/catalogos/{catalogo}/{item_id}")
def modificar_item(
    catalogo: str, item_id: int, datos: CatalogoIn, ctx: Contexto = Depends(_admin), db: Session = Depends(get_db)
):
    modelo, entidad = _modelo(catalogo)
    obj = db.get(modelo, item_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Elemento inexistente.")
    valores = {"nombre": datos.nombre, "activo": datos.activo}
    diff = audit.cambios(obj, valores)
    if diff:
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un elemento con ese nombre.")
        audit.registrar(db, ctx, "modificar", entidad, obj.id, detalle={"cambios": diff})
        db.commit()
    return _catalogo_out(obj)


# ---------------------------------------------------------------- numeración de actuaciones


@router.get("/numeracion/{anio}")
def ver_numeracion(anio: int, ctx: Contexto = Depends(_admin), db: Session = Depends(get_db)):
    ultimo = db.execute(
        select(func.max(Caso.numero_actuacion)).where(Caso.anio_actuacion == anio)
    ).scalar_one()
    return {"anio": anio, "proximo": proximo(db, f"caso-{anio}"), "mayor_registrado": ultimo}


@router.put("/numeracion")
def fijar_numeracion(datos: NumeracionIn, ctx: Contexto = Depends(_admin), db: Session = Depends(get_db)):
    """Define el próximo N° de actuación del año (por ejemplo, para continuar la numeración en papel)."""
    ultimo = db.execute(
        select(func.max(Caso.numero_actuacion)).where(Caso.anio_actuacion == datos.anio)
    ).scalar_one()
    if ultimo is not None and datos.proximo <= ultimo:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ya hay actuaciones registradas hasta el N° {ultimo}/{datos.anio}: el próximo debe ser mayor.",
        )
    anterior = proximo(db, f"caso-{datos.anio}")
    fijar_proximo(db, f"caso-{datos.anio}", datos.proximo)
    audit.registrar(
        db, ctx, "fijar_numeracion", "actuacion", datos.anio,
        detalle={"anio": datos.anio, "proximo_anterior": anterior, "proximo": datos.proximo},
    )
    db.commit()
    return {"anio": datos.anio, "proximo": datos.proximo, "mayor_registrado": ultimo}
