from fastapi import FastAPI

app = FastAPI(title="Izishop Backend API")

# Routers will be included here
# from .routers import auth, products, orders, payments, deliveries, admin
# app.include_router(auth.router, prefix="/auth", tags=["auth"])
# app.include_router(products.router, prefix="/products", tags=["products"])
# app.include_router(orders.router, prefix="/orders", tags=["orders"])
# app.include_router(payments.router, prefix="/payments", tags=["payments"])
# app.include_router(deliveries.router, prefix="/deliveries", tags=["deliveries"])
# app.include_router(admin.router, prefix="/admin", tags=["admin"])

@app.get("/")
def root():
    return {"message": "Welcome to Izishop Backend API"} 