from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.health import router as health_router
from app.api.users import router as users_router
from app.api.companies import router as companies_router
from app.api.portfolios import router as portfolios_router
from app.api.market import router as market_router

app = FastAPI(title="Investment Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(companies_router, prefix="/api")
app.include_router(portfolios_router, prefix="/api")
app.include_router(market_router, prefix="/api")


@app.get("/")
def root():
    return {"status": "Backend is working"}
