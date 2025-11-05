
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from supabase_client import supabase
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
import os

router = APIRouter(prefix="/auth", tags=["Auth"])

# 🔑 Configuración JWT
SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# 🔒 Argon2 para hashing de contraseñas
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# ==============================
# MODELOS Pydantic
# ==============================
class RegisterRequest(BaseModel):
    nombre: str
    email: str
    password: str
    rol: str = "usuario"

class LoginRequest(BaseModel):
    email: str
    password: str

# ==============================
# FUNCIONES AUXILIARES
# ==============================
def hash_password(password: str) -> str:
    """Genera un hash seguro usando Argon2"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica la contraseña usando Argon2"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    """Crea un token JWT con expiración configurable"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM), expire

# ==============================
# REGISTRO DE USUARIO
# ==============================
@router.post("/register")
async def register(request: RegisterRequest):
    try:
        email = request.email.strip().lower()
        nombre = request.nombre.strip()
        rol = request.rol

        # Verificar si el usuario ya existe
        existing = supabase.table("usuarios").select("*").eq("email", email).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="El usuario ya existe")

        hashed_password = hash_password(request.password)

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

# ==============================
# LOGIN DE USUARIO
# ==============================
@router.post("/login")
async def login(request: LoginRequest):
    try:
        email = request.email.strip().lower()
        password = request.password

        res = supabase.table("usuarios").select("*").eq("email", email).execute()
        if not res.data:
            raise HTTPException(status_code=401, detail="Credenciales no válidas")

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
