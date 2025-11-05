from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse
from supabase_client import supabase
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
import os

router = APIRouter(prefix="/auth", tags=["Auth"])

# Configuración JWT
SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
MAX_PASSWORD_LENGTH = 72  

# Funciones auxiliares
def hash_password(password: str) -> str:
    truncated = password[:MAX_PASSWORD_LENGTH] 
    return pwd_context.hash(truncated)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    truncated = plain_password[:MAX_PASSWORD_LENGTH]
    return pwd_context.verify(truncated, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM), expire

#  Registro
@router.post("/register")
async def register(
    nombre: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    rol: str = Form("usuario")
):
    try:
        email = email.strip().lower()
        nombre = nombre.strip()

        existing = supabase.table("usuarios").select("*").eq("email", email).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="El usuario ya existe")

        hashed_password = hash_password(password)

        new_user = {
            "nombre": nombre,
            "email": email,
            "password": hashed_password,
            "rol": rol,
            "fecha_creacion": datetime.utcnow().isoformat()
        }

        supabase.table("usuarios").insert(new_user).execute()

        return {"message": "Usuario registrado correctamente"}

    except HTTPException as e:
        raise e
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

#  Login
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
