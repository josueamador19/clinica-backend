from fastapi import APIRouter, Form, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from supabase_client import supabase
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
import uuid
import os
from typing import Optional

router = APIRouter(prefix="/auth", tags=["Auth"])

# 🔑 Configuración JWT
SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Argon2
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# 🔒 Funciones auxiliares
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM), expire

# 🧩 Registro de usuario (igual que usuarios.py, con Argon2)
@router.post("/register")
async def register(
    nombre: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    rol: str = Form("usuario"),
    telefono: str = Form(""),
    sucursal_id: str = Form(None),
    foto: Optional[UploadFile] = File(None)
):
    try:
        email = email.strip().lower()
        nombre = nombre.strip()

        # Revisar si existe
        existing = supabase.table("usuarios").select("*").eq("email", email).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="El usuario ya existe")

        # Subida de foto
        foto_url = None
        if foto:
            file_data = await foto.read()
            unique_filename = f"{uuid.uuid4()}_{foto.filename}"
            supabase.storage.from_("usuarios").upload(unique_filename, file_data)
            foto_url = supabase.storage.from_("usuarios").get_public_url(unique_filename)

        hashed_password = hash_password(password)

        new_user = {
            "nombre": nombre,
            "email": email,
            "password": hashed_password,
            "rol_id": rol,
            "telefono": telefono,
            "sucursal_id": sucursal_id,
            "foto_url": foto_url,
            "fecha_creacion": datetime.utcnow().isoformat()
        }

        res = supabase.table("usuarios").insert(new_user).execute()
        if not res.data:
            return JSONResponse({"error": "No se pudo crear el usuario"}, status_code=400)

        user_data = {k: v for k, v in res.data[0].items() if k != "password"}

        return {"message": "Usuario registrado correctamente", "user": user_data}

    except HTTPException as e:
        raise e
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

# 🔐 Login
@router.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...)
):
    try:
        email = email.strip().lower()
        res = supabase.table("usuarios").select("*").eq("email", email).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Credenciales no válidas")

        user = res.data[0]
        if not verify_password(password, user.get("password", "")):
            raise HTTPException(status_code=401, detail="Credenciales no válidas")

        access_token, expire = create_access_token({"sub": str(user["id"])})

        user_data = {k: v for k, v in user.items() if k != "password"}

        return {
            "message": "Login exitoso",
            "access_token": access_token,
            "token_expiration": int(expire.timestamp() * 1000),
            "user": user_data
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
