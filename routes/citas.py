from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse
from supabase_client import supabase
from datetime import datetime, timedelta

router = APIRouter()

# UUID del rol médico 
MEDICO_ROLE_ID = "5770e7d5-c449-4094-bbe1-fd52ee6fe75f"

# Obtener todos los médicos
@router.get("/medicos")
async def get_medicos():
    try:
        res = supabase.table("usuarios").select("id,nombre,email,rol_id,sucursal_id").eq("rol_id", MEDICO_ROLE_ID).execute()
        medicos = res.data

        for medico in medicos:
            horarios_res = supabase.table("horarios").select("*").eq("medico_id", medico["id"]).execute()
            medico["horarios"] = horarios_res.data or []

            sucursal_res = supabase.table("sucursales").select("*").eq("id", medico["sucursal_id"]).execute()
            medico["sucursal"] = sucursal_res.data[0] if sucursal_res.data else None

        return medicos

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
# Obtener disponibilidad de un médico con filtros opcionales
@router.get("/medicos/{medico_id}/disponibilidad")
async def get_disponibilidad(medico_id: str, sucursal_id: str = None, fecha: str = None):
    try:
        horarios_res = supabase.table("horarios").select("*").eq("medico_id", medico_id).execute()
        horarios = horarios_res.data or []

        if not horarios:
            return JSONResponse({"error": "No hay horarios para este médico"}, status_code=400)

        citas_res = supabase.table("citas").select("fecha,hora,estado,sucursal_id").eq("medico_id", medico_id).execute()
        citas = citas_res.data or []

        disponibilidad = []
        hoy = datetime.now().date()
        dias_a_ver = 14
        dias_es = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]

        for dia_offset in range(dias_a_ver):
            fecha_actual = hoy + timedelta(days=dia_offset)
            fecha_str = fecha_actual.strftime("%Y-%m-%d")
            dia_semana_str = dias_es[fecha_actual.weekday()]

            # Si se pasó fecha por query, solo considerar esa
            if fecha and fecha != fecha_str:
                continue

            for h in horarios:
                # Filtrar por sucursal si se pasó
                if sucursal_id and str(h["sucursal_id"]) != str(sucursal_id):
                    continue
                if h["dia_semana"] != dia_semana_str:
                    continue

                hora_inicio = datetime.strptime(h["hora_inicio"], "%H:%M:%S")
                hora_fin = datetime.strptime(h["hora_fin"], "%H:%M:%S")
                hora_actual = hora_inicio
                horas_disponibles = []

                while hora_actual < hora_fin:
                    hora_str = hora_actual.strftime("%H:%M")
                    ocupada = any(
                        c["fecha"] == fecha_str and
                        c["hora"] == hora_str and
                        c["estado"] == "pendiente" and
                        (not sucursal_id or str(c["sucursal_id"]) == str(sucursal_id))
                        for c in citas
                    )
                    if not ocupada:
                        horas_disponibles.append(hora_str)
                    hora_actual += timedelta(minutes=30)

                if horas_disponibles:
                    sucursal_res = supabase.table("sucursales").select("nombre").eq("id", h["sucursal_id"]).execute()
                    sucursal_nombre = sucursal_res.data[0]["nombre"] if sucursal_res.data else "Desconocida"
                    disponibilidad.append({
                        "fecha": fecha_str,
                        "sucursal_id": h["sucursal_id"],
                        "sucursal_nombre": sucursal_nombre,
                        "horas_disponibles": horas_disponibles
                    })

        return disponibilidad

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

# Crear cita con validación de disponibilidad real
@router.post("/citas")
async def create_cita(
    paciente_id: str = Form(...),
    medico_id: str = Form(...),
    sucursal_id: str = Form(...),
    fecha: str = Form(...),
    hora: str = Form(...),
    estado: str = Form("pendiente"),
    comentarios: str = Form("")
):
    try:
        # Obtener horarios del médico en la sucursal
        horarios_res = supabase.table("horarios").select("*").eq("medico_id", medico_id).eq("sucursal_id", sucursal_id).execute()
        horarios = horarios_res.data or []

        if not horarios:
            return JSONResponse({"error": "El médico no tiene horarios en esta sucursal"}, status_code=400)

        # Obtener citas existentes del médico
        citas_res = supabase.table("citas").select("*").eq("medico_id", medico_id).execute()
        citas = citas_res.data or []

        # Validar si la fecha y hora están dentro de algún horario disponible
        disponible = False
        fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
        dias_es = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
        dia_semana_str = dias_es[fecha_dt.weekday()]

        for h in horarios:
            if h["dia_semana"] != dia_semana_str:
                continue
            hora_inicio = datetime.strptime(h["hora_inicio"], "%H:%M:%S")
            hora_fin = datetime.strptime(h["hora_fin"], "%H:%M:%S")
            hora_dt = datetime.strptime(hora, "%H:%M")

            if hora_inicio <= hora_dt < hora_fin:
                # Verificar que no haya cita pendiente en esa fecha y hora
                ocupada = any(
                    c["fecha"] == fecha and
                    c["hora"] == hora and
                    c["estado"] == "pendiente"
                    for c in citas
                )
                if not ocupada:
                    disponible = True
                break

        if not disponible:
            return JSONResponse({"error": "El médico no está disponible en la fecha y hora seleccionadas"}, status_code=400)

        data = {
            "paciente_id": paciente_id,
            "medico_id": medico_id,
            "sucursal_id": sucursal_id,
            "fecha": fecha,
            "hora": hora,
            "estado": estado,
            "comentarios": comentarios
        }

        insert_res = supabase.table("citas").insert(data).execute()
        if not insert_res.data:
            return JSONResponse({"error": "No se pudo crear la cita"}, status_code=400)

        return JSONResponse({"message": "Cita creada correctamente", "cita": insert_res.data[0]}, status_code=201)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

# Obtener todas las citas futuras de un paciente
@router.get("/citas/futuras/{paciente_id}")
async def get_citas_futuras(paciente_id: str):
    try:
        hoy = datetime.now().strftime("%Y-%m-%d")

        res = supabase.table("citas").select("*") \
            .eq("paciente_id", paciente_id) \
            .gte("fecha", hoy) \
            .order("fecha", desc=False) \
            .order("hora", desc=False) \
            .execute()

        citas = res.data or []

        dias_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

        citas_enriquecidas = []
        for cita in citas:
            # Obtener medico
            medico_res = supabase.table("usuarios").select("nombre").eq("id", cita["medico_id"]).execute()
            medico_nombre = medico_res.data[0]["nombre"] if medico_res.data else "Desconocido"

            # Obtener sucursal
            sucursal_res = supabase.table("sucursales").select("nombre").eq("id", cita["sucursal_id"]).execute()
            sucursal_nombre = sucursal_res.data[0]["nombre"] if sucursal_res.data else "Desconocida"

            # Calcular día de la semana
            fecha_dt = datetime.strptime(cita["fecha"], "%Y-%m-%d")
            dia_semana = dias_es[fecha_dt.weekday()]
            fecha_formateada = f"{dia_semana} {fecha_dt.strftime('%d/%m/%Y')}"

            citas_enriquecidas.append({
                "id": cita["id"],
                "fecha": cita["fecha"],
                "fecha_formateada": fecha_formateada,
                "hora": cita["hora"],
                "estado": cita["estado"],
                "comentarios": cita.get("comentarios", ""),
                "medico": medico_nombre,
                "sucursal": sucursal_nombre
            })

        return citas_enriquecidas

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@router.patch("/citas/{cita_id}/cancelar")
async def cancelar_cita(cita_id: str):
    try:
        update_res = supabase.table("citas").update({"estado": "cancelada"}).eq("id", cita_id).execute()
        if not update_res.data:
            return JSONResponse({"error": "No se encontró la cita"}, status_code=404)

        return JSONResponse({"message": "Cita cancelada correctamente"}, status_code=200)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    
@router.get("/citas/historial/{paciente_id}")
async def get_historial_citas(paciente_id: str):
    try:
        hoy = datetime.now().date()

        res = supabase.table("citas").select("*").eq("paciente_id", paciente_id).order("fecha", desc=True).execute()
        citas = res.data or []

        dias_es = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]

        for c in citas:
            fecha_dt = datetime.strptime(c["fecha"], "%Y-%m-%d").date()
            c["fecha_formateada"] = fecha_dt.strftime("%d/%m/%Y")
            c["dia"] = dias_es[fecha_dt.weekday()]

            # traer nombre de medico
            med_res = supabase.table("usuarios").select("nombre").eq("id", c["medico_id"]).execute()
            c["medico"] = med_res.data[0]["nombre"] if med_res.data else "Desconocido"

            # traer nombre de sucursal
            suc_res = supabase.table("sucursales").select("nombre").eq("id", c["sucursal_id"]).execute()
            c["sucursal"] = suc_res.data[0]["nombre"] if suc_res.data else "Desconocida"

        return citas

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

##Reagendar Citas

@router.get("/admin/medicos/{medico_id}/disponibilidad")
async def admin_disponibilidad(medico_id: str, fecha: str = None):
    try:
        # Obtener todos los horarios del médico (todas las sucursales)
        horarios_res = supabase.table("horarios").select("*").eq("medico_id", medico_id).execute()
        horarios = horarios_res.data or []

        if not horarios:
            return JSONResponse({"error": "No hay horarios para este médico"}, status_code=400)

        # Obtener todas las citas del médico
        citas_res = supabase.table("citas").select("fecha,hora,estado,sucursal_id").eq("medico_id", medico_id).execute()
        citas = citas_res.data or []

        disponibilidad = []
        hoy = datetime.now().date()
        dias_a_ver = 14
        dias_es = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]

        for dia_offset in range(dias_a_ver):
            fecha_actual = hoy + timedelta(days=dia_offset)
            fecha_str = fecha_actual.strftime("%Y-%m-%d")
            dia_semana_str = dias_es[fecha_actual.weekday()]

            if fecha and fecha != fecha_str:
                continue

            # Agrupar por sucursal
            sucursales = set(h["sucursal_id"] for h in horarios if h["dia_semana"] == dia_semana_str)
            for sucursal_id in sucursales:
                horas_disponibles = []

                # Filtrar horarios de la sucursal y día
                horarios_sucursal = [h for h in horarios if h["dia_semana"] == dia_semana_str and h["sucursal_id"] == sucursal_id]

                for h in horarios_sucursal:
                    # convertir a time
                    hora_inicio = datetime.strptime(h["hora_inicio"], "%H:%M:%S").time()
                    hora_fin = datetime.strptime(h["hora_fin"], "%H:%M:%S").time()

                    hora_actual = hora_inicio
                    while hora_actual < hora_fin:
                        hora_str = hora_actual.strftime("%H:%M")
                        ocupada = any(
                            c["fecha"] == fecha_str and
                            c["hora"] == hora_str and
                            c["estado"] == "pendiente" and
                            str(c["sucursal_id"]) == str(sucursal_id)
                            for c in citas
                        )
                        if not ocupada and hora_str not in horas_disponibles:
                            horas_disponibles.append(hora_str)
                        # sumar 1 hora
                        hora_actual = (datetime.combine(datetime.today(), hora_actual) + timedelta(hours=1)).time()

                if horas_disponibles:
                    sucursal_res = supabase.table("sucursales").select("nombre").eq("id", sucursal_id).execute()
                    sucursal_nombre = sucursal_res.data[0]["nombre"] if sucursal_res.data else "Desconocida"
                    disponibilidad.append({
                        "fecha": fecha_str,
                        "sucursal_id": sucursal_id,
                        "sucursal_nombre": sucursal_nombre,
                        "horas_disponibles": sorted(horas_disponibles)
                    })

        return disponibilidad

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
# --- Endpoint para reagendar cita ---
@router.patch("/citas/{cita_id}/reagendar")
async def reagendar_cita(
    cita_id: str,
    fecha: str = Query(...),
    hora: str = Query(...),
    sucursal_id: str = Query(...)
):
    try:
        # Traer la cita existente
        cita_res = supabase.table("citas").select("*").eq("id", cita_id).execute()
        if not cita_res.data:
            return JSONResponse({"error": "Cita no encontrada"}, status_code=404)
        cita = cita_res.data[0]

        medico_id = cita["medico_id"]

        # Traer horarios del médico en todas las sucursales
        horarios_res = supabase.table("horarios").select("*").eq("medico_id", medico_id).execute()
        horarios = horarios_res.data or []

        if not horarios:
            return JSONResponse({"error": "El médico no tiene horarios"}, status_code=400)

        # Traer citas pendientes del médico
        citas_res = supabase.table("citas").select("fecha,hora,estado,sucursal_id").eq("medico_id", medico_id).execute()
        citas = citas_res.data or []

        # Validar disponibilidad
        fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
        dia_semana = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"][fecha_dt.weekday()]

        disponible = False

        # Filtrar horarios del día y sucursal
        horarios_validos = [h for h in horarios if h["dia_semana"] == dia_semana and str(h["sucursal_id"]) == str(sucursal_id)]

        for h in horarios_validos:
            hora_inicio = datetime.strptime(h["hora_inicio"], "%H:%M:%S").time()
            hora_fin = datetime.strptime(h["hora_fin"], "%H:%M:%S").time()

            hora_dt = datetime.strptime(hora, "%H:%M").time()

            if hora_inicio <= hora_dt < hora_fin:
                # Verificar si ya hay cita pendiente en esa fecha, hora y sucursal
                ocupada = any(
                    c["fecha"] == fecha and
                    c["hora"] == hora and
                    c["estado"] == "pendiente" and
                    str(c["sucursal_id"]) == str(sucursal_id)
                    for c in citas
                )
                if not ocupada:
                    disponible = True
                break

        if not disponible:
            return JSONResponse({"error": "El médico no está disponible en la fecha, hora o sucursal seleccionadas"}, status_code=400)

        # Actualizar cita
        update_res = supabase.table("citas").update({
            "fecha": fecha,
            "hora": hora,
            "sucursal_id": sucursal_id
        }).eq("id", cita_id).execute()

        if not update_res.data:
            return JSONResponse({"error": "No se pudo reagendar la cita"}, status_code=400)

        return JSONResponse({"message": "Cita reagendada correctamente", "cita": update_res.data[0]}, status_code=200)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    
# Endpoint para que el admin vea las citas del paciente y del medico

@router.get("/citas/todas")
async def get_all_citas():
    try:
        citas_res = supabase.table("citas").select("*").execute()
        citas = citas_res.data or []
        dias_es = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]

        citas_enriquecidas = []
        for c in citas:
            # traer nombres
            pac_res = supabase.table("usuarios").select("nombre").eq("id", c["paciente_id"]).execute()
            med_res = supabase.table("usuarios").select("nombre").eq("id", c["medico_id"]).execute()
            suc_res = supabase.table("sucursales").select("nombre").eq("id", c["sucursal_id"]).execute()

            fecha_dt = datetime.strptime(c["fecha"], "%Y-%m-%d").date()
            dia_semana = dias_es[fecha_dt.weekday()]

            citas_enriquecidas.append({
                "id": c["id"],
                "paciente": pac_res.data[0]["nombre"] if pac_res.data else "Desconocido",
                "medico": med_res.data[0]["nombre"] if med_res.data else "Desconocido",
                "sucursal": suc_res.data[0]["nombre"] if suc_res.data else "Desconocida",
                "fecha": c["fecha"],
                "hora": c["hora"],
                "fecha_formateada": f"{dia_semana} {fecha_dt.strftime('%d/%m/%Y')}",
                "estado": c["estado"]
            })

        return citas_enriquecidas
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
