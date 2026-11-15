import os
from pydantic import BaseModel

class Settings(BaseModel):
    PROJECT_NAME: str = "EventSphere"
    VERSION: str = "1.0.0"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "eventsphere-super-secret-key-change-in-production-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./eventsphere.db")

    # Multi-Agent Policies & Decision Rules
    VENUE_TURNAROUND_BUFFER_MINUTES: int = 60      # 1 hour cleaning/prep between activities
    PEAK_HOUR_START: int = 18                      # 18:00
    PEAK_HOUR_END: int = 22                        # 22:00
    WEEKEND_PRICE_MULTIPLIER: float = 1.25         # +25% on Sat/Sun
    PEAK_HOUR_MULTIPLIER: float = 1.15             # +15% on peak hours
    MAX_TICKETS_PER_BOOKING: int = 6               # Max tickets in one booking
    CART_HOLD_DURATION_MINUTES: int = 10           # 10 min cart hold
    WAITLIST_HOLD_DURATION_MINUTES: int = 15       # 15 min waitlist reservation
    SUSPICIOUS_SCAN_WINDOW_SECONDS: int = 30       # Repeated scans within 30s trigger fraud flag

    # Refund Policy rules (hours before event start)
    REFUND_FULL_HOURS: int = 48                    # 100% refund if cancelled > 48h before event
    REFUND_PARTIAL_HOURS: int = 24                 # 50% refund if cancelled between 24h and 48h
    REFUND_PARTIAL_RATE: float = 0.50

settings = Settings()
