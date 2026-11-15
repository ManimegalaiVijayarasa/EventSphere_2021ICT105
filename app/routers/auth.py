from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserLogin, UserOut, Token
from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_user_optional,
    generate_csrf_token
)

router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")

# --- HTML Page Routes ---
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: User = Depends(get_current_user_optional)):
    if user:
        if user.role == "admin":
            return RedirectResponse(url="/admin", status_code=303)
        elif user.role == "staff":
            return RedirectResponse(url="/scanner", status_code=303)
        return RedirectResponse(url="/", status_code=303)

    session_id = request.cookies.get("session_id", "guest-session")
    csrf_token = generate_csrf_token(session_id)
    response = templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "user": None,
            "csrf_token": csrf_token,
            "error": None
        }
    )
    if "session_id" not in request.cookies:
        response.set_cookie("session_id", session_id, httponly=True)
    return response

@router.post("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not verify_password(password, user.hashed_password):
        session_id = request.cookies.get("session_id", "guest-session")
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "user": None,
                "csrf_token": generate_csrf_token(session_id),
                "error": "Invalid email or password.",
                "email": email
            },
            status_code=400
        )

    token = create_access_token(data={"sub": user.email, "role": user.role, "id": user.id})

    # Redirect based on role
    redirect_target = "/"
    if user.role == "admin":
        redirect_target = "/admin"
    elif user.role == "staff":
        redirect_target = "/scanner"

    redirect = RedirectResponse(url=redirect_target, status_code=303)
    redirect.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    return redirect

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: User = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/", status_code=303)
    session_id = request.cookies.get("session_id", "guest-session")
    csrf_token = generate_csrf_token(session_id)
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "user": None,
            "csrf_token": csrf_token,
            "error": None
        }
    )

@router.post("/register", response_class=HTMLResponse)
def register_form(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    clean_email = email.strip().lower()
    existing = db.query(User).filter(User.email == clean_email).first()
    if existing:
        session_id = request.cookies.get("session_id", "guest-session")
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "user": None,
                "csrf_token": generate_csrf_token(session_id),
                "error": "An account with this email already exists.",
                "full_name": full_name,
                "email": email
            },
            status_code=400
        )

    new_user = User(
        email=clean_email,
        full_name=full_name.strip(),
        hashed_password=hash_password(password),
        role="attendee"
    )
    db.add(new_user)
    db.commit()

    token = create_access_token(data={"sub": new_user.email, "role": new_user.role, "id": new_user.id})
    redirect = RedirectResponse(url="/", status_code=303)
    redirect.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    return redirect

@router.get("/logout")
def logout():
    redirect = RedirectResponse(url="/login", status_code=303)
    redirect.delete_cookie("access_token")
    return redirect

# --- REST API Endpoints ---
@router.post("/api/auth/register", response_model=UserOut)
def api_register(payload: UserCreate, db: Session = Depends(get_db)):
    clean_email = payload.email.strip().lower()
    if db.query(User).filter(User.email == clean_email).first():
        raise HTTPException(status_code=400, detail="Email already registered.")

    # Public API registration is restricted to attendees
    role = "attendee"
    user = User(
        email=clean_email,
        full_name=payload.full_name.strip(),
        hashed_password=hash_password(payload.password),
        role=role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/api/auth/token", response_model=Token)
@router.post("/api/auth/login", response_model=Token)
def api_login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token(data={"sub": user.email, "role": user.role, "id": user.id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "full_name": user.full_name
    }

@router.get("/api/auth/me", response_model=UserOut)
def api_me(current_user: User = Depends(get_current_user)):
    return current_user
