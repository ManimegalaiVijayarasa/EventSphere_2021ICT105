import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.agents import agent_bus
from app.agents.base import Performative
from app.schemas import AgentMessage

# Import routers
from app.routers import auth, events, bookings, venues, staff, admin, agents_api

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("eventsphere.main")

# Proactive Agent Background Task
async def proactive_agent_worker():
    """Continuous async background worker executing proactive sweeps on a timer without user input."""
    logger.info("Starting Proactive Agent background scheduler...")
    while True:
        try:
            await asyncio.sleep(15)  # Every 15 seconds
            db = SessionLocal()
            try:
                # 1. Proactive Waitlist sweep (re-offers expired holds or releases seats)
                sweep_msg = AgentMessage(
                    message_id=str(uuid.uuid4()),
                    conversation_id=f"proactive-sweep-{uuid.uuid4().hex[:6]}",
                    sender="TimerScheduler",
                    receiver="WaitlistAgent",
                    performative=Performative.REQUEST,
                    content={"action": "PROACTIVE_SWEEP"}
                )
                agent_bus.send(sweep_msg, db=db)
            except Exception as e:
                logger.error(f"Error during proactive agent sweep: {e}")
            finally:
                db.close()
        except asyncio.CancelledError:
            logger.info("Proactive agent worker cancelled.")
            break
        except Exception as e:
            logger.error(f"Unexpected worker exception: {e}")
            await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables if not exist
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized.")

    # Start proactive background worker
    worker_task = asyncio.create_task(proactive_agent_worker())
    yield
    # Shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("EventSphere shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Mobile-friendly multi-agent venue booking and digital ticketing platform where every booking decision is made by cooperating software agents.",
    lifespan=lifespan
)

# Mount Static Files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include Routers
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(bookings.router)
app.include_router(venues.router)
app.include_router(staff.router)
app.include_router(admin.router)
app.include_router(agents_api.router)

templates = Jinja2Templates(directory="app/templates")

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return {"error": "Not Found", "detail": str(exc.detail if hasattr(exc, "detail") else exc)}
    return templates.TemplateResponse(
        request=request,
        name="base.html",
        context={
            "user": None,
            "content_block": "<div class='container text-center py-5'><h2>404 - Page Not Found</h2><p>The page you requested does not exist.</p><a href='/' class='btn btn-primary'>Return Home</a></div>"
        },
        status_code=404
    )
