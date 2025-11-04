from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from supabase_client import supabase
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
import os

router = APIRouter(prefix="/auth", tags=["Auth"])

SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# 🔐 Modelos Pydantic
class LoginRequest(BaseModel):
    email: str
    password: str


# 🔑 Funciones auxiliares
def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt solo usa los primeros 72 bytes, así que truncamos antes de verificar
    truncated = plain_password[:72]
    return pwd_context.verify(truncated, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM), expire


# 🔐 Endpoint de login usando JSON
@router.post("/login")
async def login(request: LoginRequest):
    try:
        email = request.email.strip().lower()
        password = request.password

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
