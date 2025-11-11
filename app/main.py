from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db.session import engine, Base
from app.api import router as api_router
from app.api import auth
from app.api import gateway as gateway_router
from app.middleware.rate_limiter import RateLimitMiddleware
from app import __version__

app = FastAPI(
    title="BridgeAI Backend",
    version=__version__
)

# ✅ Define allowed frontend origins
origins = [
    "http://localhost:3000",  # your frontend React app
]

# ✅ Add CORS middleware only once
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # allow GET, POST, PUT, DELETE, OPTIONS
    allow_headers=["*"],  # allow all headers
)

# Add rate limiting middleware. This is an in-memory limiter suitable for dev or
# single-process deployments. For production, replace with a distributed limiter.
app.add_middleware(RateLimitMiddleware)

# ✅ Create database tables (optional)
# Base.metadata.create_all(bind=engine)

# ✅ Include routers
app.include_router(api_router, prefix="/api")
app.include_router(auth.router)  # make sure this defines /auth/token
app.include_router(gateway_router.router)

@app.get("/")
def root():
    return {
        "message": "BridgeAI backend running",
        "version": __version__
    }