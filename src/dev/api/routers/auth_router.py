from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from src.dev.utils.db_utils import get_sys_db
from src.dev.database.models import User
from src.dev.utils.auth import get_password_hash, verify_password, create_access_token
from src.dev.api.dto import UserRegister, Token

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/register", response_model=Token)
def register(user_in: UserRegister, db: Session = Depends(get_sys_db)):
    # 检查用户是否存在
    db_user = db.query(User).filter(User.username == user_in.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    # 创建用户
    hashed_pwd = get_password_hash(user_in.password)
    new_user = User(username=user_in.username, password_hash=hashed_pwd, email=user_in.email)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 自动登录
    access_token = create_access_token(data={"sub": new_user.username})
    return {"access_token": access_token, "token_type": "bearer", "user_id": new_user.id, "username": new_user.username}


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_sys_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id, "username": user.username}