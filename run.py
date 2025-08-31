from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create simple FastAPI app
app = FastAPI(
    title="Izishop Backend API",
    description="Backend API for Izishop e-commerce platform",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory storage for demonstration
users = []
shops = []
products = []

# Simple models
class User:
    def __init__(self, id, email, first_name, last_name, role="user"):
        self.id = id
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.role = role
        self.is_active = True

class Shop:
    def __init__(self, id, name, description="", is_active=True):
        self.id = id
        self.name = name
        self.description = description
        self.is_active = is_active

class Product:
    def __init__(self, id, name, description="", price=0.0):
        self.id = id
        self.name = name
        self.description = description
        self.price = price

# Simple dependency to get current user
def get_current_user():
    # For demonstration, return a mock user
    return User("1", "test@example.com", "Test", "User", "SHOP_OWNER")

# Health check endpoint
@app.get("/")
def root():
    """Root endpoint for API health check."""
    return {
        "message": "Welcome to Izishop Backend API",
        "status": "healthy",
        "version": "1.0.0"
    }

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

# User endpoints
@app.post("/api/auth/register")
def register(user_data: dict):
    """Register a new user."""
    try:
        # Check if user already exists
        existing_user = next((user for user in users if user.email == user_data.get("email")), None)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already exists"
            )
        
        new_user = User(
            id=str(len(users) + 1),
            email=user_data.get("email", ""),
            first_name=user_data.get("first_name", ""),
            last_name=user_data.get("last_name", ""),
            role=user_data.get("role", "user")
        )
        
        users.append(new_user)
        logger.info(f"User registered: {new_user.email}")
        
        return {
            "id": new_user.id,
            "email": new_user.email,
            "first_name": new_user.first_name,
            "last_name": new_user.last_name,
            "role": new_user.role,
            "is_active": new_user.is_active
        }
    except Exception as e:
        logger.error(f"Error registering user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user"
        )

@app.post("/api/auth/login")
def login(credentials: dict):
    """Login user."""
    try:
        user = next((user for user in users if user.email == credentials.get("email")), None)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        logger.info(f"User logged in: {user.email}")
        
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "is_active": user.is_active
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error logging in user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to login"
        )

# Shop endpoints
@app.post("/api/shops/create")
def create_shop(shop_data: dict, current_user: User = Depends(get_current_user)):
    """Create a new shop."""
    try:
        # Check if user already has a shop
        existing_shop = next((shop for shop in shops if shop.id == current_user.id), None)
        if existing_shop:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already has a shop"
            )
        
        # Create new shop
        new_shop = Shop(
            id=str(len(shops) + 1),
            name=shop_data.get("name", ""),
            description=shop_data.get("description", "")
        )
        
        shops.append(new_shop)
        logger.info(f"Shop created: {new_shop.name}")
        
        return {
            "id": new_shop.id,
            "name": new_shop.name,
            "description": new_shop.description,
            "is_active": new_shop.is_active
        }
    except Exception as e:
        logger.error(f"Error creating shop: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create shop"
        )

@app.get("/api/shops")
def get_shops():
    """Get all shops."""
    try:
        return [{
            "id": shop.id,
            "name": shop.name,
            "description": shop.description,
            "is_active": shop.is_active
        } for shop in shops]
    except Exception as e:
        logger.error(f"Error getting shops: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve shops"
        )

@app.get("/api/shops/{shop_id}")
def get_shop(shop_id: str):
    """Get a specific shop by ID."""
    try:
        shop = next((shop for shop in shops if shop.id == shop_id), None)
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        return {
            "id": shop.id,
            "name": shop.name,
            "description": shop.description,
            "is_active": shop.is_active
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting shop {shop_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve shop"
        )

# Product endpoints
@app.post("/api/products/create")
def create_product(product_data: dict, current_user: User = Depends(get_current_user)):
    """Create a new product."""
    try:
        new_product = Product(
            id=str(len(products) + 1),
            name=product_data.get("name", ""),
            description=product_data.get("description", ""),
            price=product_data.get("price", 0.0)
        )
        
        products.append(new_product)
        logger.info(f"Product created: {new_product.name}")
        
        return {
            "id": new_product.id,
            "name": new_product.name,
            "description": new_product.description,
            "price": new_product.price
        }
    except Exception as e:
        logger.error(f"Error creating product: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product"
        )

@app.get("/api/products")
def get_products():
    """Get all products."""
    try:
        return [{
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": product.price
        } for product in products]
    except Exception as e:
        logger.error(f"Error getting products: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve products"
        )

@app.get("/api/products/{product_id}")
def get_product(product_id: str):
    """Get a specific product by ID."""
    try:
        product = next((product for product in products if product.id == product_id), None)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        return {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": product.price
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting product {product_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve product"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)