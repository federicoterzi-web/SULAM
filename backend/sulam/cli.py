"""Comandos de administración de SULAM.

Uso:  python -m sulam.cli <comando>   (o simplemente `sulam <comando>` si está instalado)

  migrar              Crea o actualiza las tablas de la base de datos.
  inicializar         Carga catálogos y roles iniciales y crea el primer administrador.
  datos-demo          Carga usuarios y legajos FICTICIOS para probar (no usar en producción).
  servidor            Inicia la aplicación web.
  respaldar           Genera un respaldo (base + archivos) en un único .tar.gz.
  restaurar ARCHIVO   Restaura un respaldo (reemplaza los datos actuales).
  verificar-archivos  Comprueba que cada documento exista y no esté alterado.
  migrar-archivos     Copia los documentos a otro almacenamiento y verifica los hashes.
  fichas              Genera los PDF de las fichas en papel para imprimir.
"""

from __future__ import annotations

import argparse
import getpass
import io
import os
import sys
from pathlib import Path

from sqlalchemy import select


def _alembic_cfg():
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    cfg.attributes["configure_logger"] = False
    return cfg


def cmd_migrar(_args) -> None:
    from alembic import command

    command.upgrade(_alembic_cfg(), "head")
    print("Base de datos actualizada.")


def cmd_inicializar(args) -> None:
    from .db import session_factory
    from .models import Usuario
    from .seed import crear_administrador, inicializar_catalogos
    from .security import validar_password_nueva

    db = session_factory()()
    try:
        inicializar_catalogos(db)
        hay_usuarios = db.execute(select(Usuario.id)).first() is not None
        if hay_usuarios:
            db.commit()
            print("Catálogos verificados. Ya existen usuarios: no se crea otro administrador.")
            return
        password = os.environ.get("SULAM_ADMIN_PASSWORD") or getpass.getpass(
            f"Contraseña inicial para '{args.admin_usuario}': "
        )
        error = validar_password_nueva(password)
        if error:
            sys.exit(error)
        crear_administrador(db, args.admin_usuario, args.admin_nombre, password)
        db.commit()
        print(f"Administrador '{args.admin_usuario}' creado. Deberá cambiar la contraseña al ingresar.")
    finally:
        db.close()


def _pdf_ficticio(titulo: str) -> bytes:
    contenido = f"BT /F1 18 Tf 72 720 Td (DOCUMENTO FICTICIO - {titulo}) Tj ET".encode("latin-1", "replace")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(contenido) + contenido + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = io.BytesIO()
    salida.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objetos, start=1):
        offsets.append(salida.tell())
        salida.write(b"%d 0 obj\n" % i + obj + b"\nendobj\n")
    xref = salida.tell()
    salida.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1))
    for off in offsets:
        salida.write(b"%010d 00000 n \n" % off)
    salida.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref))
    return salida.getvalue()


def cmd_datos_demo(_args) -> None:
    from . import audit
    from .config import get_settings
    from .db import session_factory
    from .models import (
        Area,
        Caso,
        CasoAsignacion,
        CasoEstadoHistorial,
        Documento,
        Expediente,
        Ingreso,
        Persona,
        PersonaVinculada,
        Rol,
        TipoDocumental,
        TipoVinculo,
        Usuario,
    )
    from .numbering import nueva_actuacion, numero_ingreso, numero_legajo
    from .security import hash_password
    from .seed import PASSWORD_DEMO, PERSONAS_DEMO, USUARIOS_DEMO, inicializar_catalogos
    from .storage import almacenamiento_actual
    from .textutil import normalizar

    if get_settings().environment == "produccion":
        sys.exit("No se cargan datos de demostración en producción.")

    db = session_factory()()
    try:
        inicializar_catalogos(db)
        if db.execute(select(Persona.id)).first() is not None:
            sys.exit("La base ya tiene legajos: no se cargan datos de demostración.")

        areas = {a.nombre: a for a in db.execute(select(Area)).scalars()}
        roles = {r.nombre: r for r in db.execute(select(Rol)).scalars()}
        tipos = {t.nombre: t for t in db.execute(select(TipoDocumental)).scalars()}
        vinculos = {t.nombre: t for t in db.execute(select(TipoVinculo)).scalars()}

        usuarios = {}
        hash_demo = hash_password(PASSWORD_DEMO)
        for usuario, nombre, rol, area in USUARIOS_DEMO:
            u = db.execute(select(Usuario).where(Usuario.usuario == usuario)).scalar_one_or_none()
            if u is None:
                u = Usuario(
                    usuario=usuario, nombre_completo=nombre, password_hash=hash_demo,
                    debe_cambiar_password=False, area_id=areas[area].id,
                )
                u.roles = [roles[rol]]
                db.add(u)
            usuarios[usuario] = u
        db.flush()

        personas = []
        for apellidos, nombres, tipo_doc, numero, nac, localidad in PERSONAS_DEMO:
            p = Persona(
                numero_legajo=numero_legajo(db),
                apellidos=apellidos, nombres=nombres,
                apellidos_norm=normalizar(apellidos), nombres_norm=normalizar(nombres),
                tipo_documento=tipo_doc, numero_documento=numero,
                sin_documento=numero is None,
                motivo_sin_documento="Documento extraviado; en trámite (dato ficticio)" if numero is None else None,
                fecha_nacimiento=nac, fecha_nacimiento_aproximada=numero is None,
                localidad=localidad, domicilio="Domicilio ficticio s/n",
                creado_por=usuarios["carga"].id,
            )
            db.add(p)
            personas.append(p)
        db.flush()

        admision = areas["Departamento Admisión de Casos y Recepción de Denuncias"]
        promocion = areas["Departamento Promoción Integral de Derechos"]
        cuidados = areas["División Cuidados y Promoción de Autonomía"]
        casos_def = [
            (0, admision, "en_seguimiento", "tecnica1", False, "Situación de vulnerabilidad habitacional (ficticio)."),
            (1, promocion, "abierto", "tecnico2", False, "Solicitud de acompañamiento para trámites (ficticio)."),
            (2, admision, "abierto", "tecnica1", True, "Denuncia de posible maltrato en el ámbito familiar (ficticio)."),
            (3, cuidados, "pausado", "tecnico2", False, "Seguimiento de cuidados domiciliarios (ficticio)."),
            (4, admision, "cerrado", "tecnica1", False, "Orientación sobre prestaciones (ficticio)."),
        ]
        casos = []
        for idx, area, estado, tecnico, reservado, motivo in casos_def:
            anio, n, numero = nueva_actuacion(db)
            c = Caso(
                numero=numero, numero_actuacion=n, anio_actuacion=anio,
                persona_id=personas[idx].id, area_id=area.id,
                estado=estado, reservado=reservado, motivo=motivo, creado_por=usuarios["carga"].id,
            )
            db.add(c)
            db.flush()
            db.add(CasoEstadoHistorial(caso_id=c.id, estado_nuevo="abierto", usuario_id=usuarios["carga"].id))
            if estado != "abierto":
                db.add(CasoEstadoHistorial(
                    caso_id=c.id, estado_anterior="abierto", estado_nuevo=estado,
                    motivo="Cambio de estado de demostración", usuario_id=usuarios[tecnico].id,
                ))
            db.add(CasoAsignacion(caso_id=c.id, usuario_id=usuarios[tecnico].id, asignado_por=usuarios["direccion"].id))
            casos.append(c)
        db.flush()

        db.add(PersonaVinculada(
            persona_id=personas[0].id, tipo_vinculo_id=vinculos["Familiar"].id,
            apellidos="PÉREZ", nombres="Laura (sobrina, ficticio)", telefono="381-000-0000",
            creado_por=usuarios["carga"].id,
        ))
        db.add(PersonaVinculada(
            persona_id=personas[2].id, tipo_vinculo_id=vinculos["Denunciante"].id,
            apellidos="VECINO", nombres="Identidad reservada (ficticio)", reservado=True,
            creado_por=usuarios["carga"].id,
        ))
        db.add(Expediente(
            numero="EXP-1234/310-D-2026", tipo="administrativo", organismo="Dirección de Adultos Mayores",
            caratula="Pérez Rosa Elvira s/ solicitud (ficticio)", persona_id=personas[0].id,
            caso_id=casos[0].id, creado_por=usuarios["mesa"].id,
        ))
        db.add(Expediente(
            numero="J-5678/2026", tipo="judicial", organismo="Juzgado ficticio",
            caratula="Fernández de López María Inés s/ protección (ficticio)", persona_id=personas[2].id,
            caso_id=casos[2].id, creado_por=usuarios["mesa"].id,
        ))
        db.add(Ingreso(
            numero=numero_ingreso(db), remitente="Hospital ficticio", asunto="Nota solicitando intervención",
            folios=3, persona_mencionada="Ruiz Héctor", documento_mencionado="7012844",
            tipo_documental_id=tipos["Oficio"].id, creado_por=usuarios["mesa"].id,
        ))
        db.add(Ingreso(
            numero=numero_ingreso(db), remitente="Particular", asunto="Presentación espontánea de vecina",
            folios=1, persona_mencionada="Señora de apellido Morales", creado_por=usuarios["mesa"].id,
        ))

        almacen = almacenamiento_actual()
        for persona, caso, titulo, tipo in (
            (personas[0], casos[0], "Informe socioambiental inicial", "Informe socioambiental"),
            (personas[2], casos[2], "Acta de intervención", "Acta de acción o intervención"),
        ):
            guardado = almacen.guardar(io.BytesIO(_pdf_ficticio(titulo)))
            db.add(Documento(
                persona_id=persona.id, caso_id=caso.id, tipo_documental_id=tipos[tipo].id,
                titulo=titulo, nombre_original=f"{titulo}.pdf", mime="application/pdf",
                tamano=guardado.tamano, sha256=guardado.sha256, almacenamiento=almacen.nombre,
                clave_almacenamiento=guardado.clave, cargado_por=usuarios[
                    "tecnica1"].id,
            ))
        audit.registrar(db, None, "datos_demo", "sistema", detalle={"personas": len(personas)})
        db.commit()
        print("Datos de demostración cargados (todos FICTICIOS).")
        print(f"Usuarios: {', '.join(u for u, *_ in USUARIOS_DEMO)} — contraseña: {PASSWORD_DEMO}")
    finally:
        db.close()


def cmd_fichas(args) -> None:
    from .papel.fichas import FICHAS, NOMBRES_ARCHIVO, ficha

    destino = Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)
    for codigo in FICHAS:
        pdf, plantilla = ficha(codigo)
        ruta = destino / f"SULAM-{NOMBRES_ARCHIVO[codigo]}-v{plantilla['version']}.pdf"
        ruta.write_bytes(pdf)
        print(f"Generada: {ruta}")


def cmd_servidor(args) -> None:
    import uvicorn

    uvicorn.run("sulam.main:app", host=args.host, port=args.puerto, proxy_headers=True)


def cmd_respaldar(args) -> None:
    from .backup import respaldar

    ruta = respaldar(Path(args.destino) if args.destino else None)
    print(f"Respaldo generado: {ruta}")


def cmd_restaurar(args) -> None:
    from .backup import restaurar

    if not args.confirmar:
        sys.exit(
            "La restauración REEMPLAZA todos los datos actuales. "
            "Repita el comando agregando --confirmar para continuar."
        )
    m = restaurar(Path(args.archivo))
    print(f"Respaldo del {m['fecha']} restaurado ({len(m['archivos'])} archivos).")


def cmd_verificar_archivos(_args) -> None:
    from .db import session_factory
    from .models import Documento
    from .storage import almacenamiento_por_nombre

    db = session_factory()()
    errores = 0
    total = 0
    try:
        for d in db.execute(select(Documento)).scalars():
            total += 1
            almacen = almacenamiento_por_nombre(d.almacenamiento)
            if not almacen.verificar(d.clave_almacenamiento, d.sha256):
                errores += 1
                print(f"ERROR  {d.id}  {d.titulo}  ({d.almacenamiento}:{d.clave_almacenamiento})")
    finally:
        db.close()
    print(f"{total} documentos verificados, {errores} con problemas.")
    if errores:
        sys.exit(1)


def cmd_migrar_archivos(args) -> None:
    """Copia cada documento al almacenamiento destino, verifica el hash y
    actualiza la referencia. Nunca borra los archivos de origen."""
    from .db import session_factory
    from .models import Documento
    from .storage import almacenamiento_por_nombre, copiar

    destino = almacenamiento_por_nombre(args.hacia, Path(args.raiz) if args.raiz else None)
    db = session_factory()()
    try:
        docs = list(db.execute(select(Documento)).scalars())
        print(f"Inventario: {len(docs)} documentos.")
        for d in docs:
            origen = almacenamiento_por_nombre(d.almacenamiento)
            copia = copiar(origen, d.clave_almacenamiento, destino)
            if copia.sha256 != d.sha256 or not destino.verificar(copia.clave, d.sha256):
                db.rollback()
                sys.exit(f"Verificación fallida en {d.id}. No se modificó ninguna referencia.")
            d.almacenamiento = destino.nombre
            d.clave_almacenamiento = copia.clave
        db.commit()
        print("Migración verificada. Los archivos de origen se conservan; elimínelos solo tras comprobar el acceso.")
    finally:
        db.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="sulam", description="Administración de SULAM")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("migrar").set_defaults(func=cmd_migrar)

    p = sub.add_parser("inicializar")
    p.add_argument("--admin-usuario", default="admin")
    p.add_argument("--admin-nombre", default="Administrador del sistema")
    p.set_defaults(func=cmd_inicializar)

    sub.add_parser("datos-demo").set_defaults(func=cmd_datos_demo)

    p = sub.add_parser("fichas")
    p.add_argument("--destino", default="fichas")
    p.set_defaults(func=cmd_fichas)

    p = sub.add_parser("servidor")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--puerto", type=int, default=8000)
    p.set_defaults(func=cmd_servidor)

    p = sub.add_parser("respaldar")
    p.add_argument("--destino")
    p.set_defaults(func=cmd_respaldar)

    p = sub.add_parser("restaurar")
    p.add_argument("archivo")
    p.add_argument("--confirmar", action="store_true")
    p.set_defaults(func=cmd_restaurar)

    sub.add_parser("verificar-archivos").set_defaults(func=cmd_verificar_archivos)

    p = sub.add_parser("migrar-archivos")
    p.add_argument("--hacia", default="local")
    p.add_argument("--raiz", help="Carpeta destino (para almacenamiento local)")
    p.set_defaults(func=cmd_migrar_archivos)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
