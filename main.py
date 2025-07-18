from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database.connection import create_tables
from .routers import auth

app = FastAPI(
    title="Izishop Backend API",
    description="Backend API for Izishop e-commerce platform",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # Frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])

# Create database tables on startup
@app.on_event("startup")
async def startup_event():
    create_tables()

@app.get("/")
def root():
    return {"message": "Welcome to Izishop Backend API"} 