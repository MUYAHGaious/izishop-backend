# Izishop Backend API

This is the backend API for the Izishop e-commerce platform built with FastAPI.

## Features

- User authentication (login/register) with JWT tokens
- Password hashing with bcrypt
- SQLAlchemy ORM with PostgreSQL/SQLite support
- CORS middleware for frontend integration
- Pydantic validation for request/response models

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the backend directory with the following variables:

```env
# Database Configuration
DATABASE_URL=sqlite:///./izishop.db

# Security
SECRET_KEY=your-super-secret-key-change-this-in-production

# Application URLs
FRONTEND_BASE_URL=http://localhost:3000
BACKEND_BASE_URL=http://localhost:8000
```

### 3. Run the Application

```bash
# Option 1: Using the run script
python run.py

# Option 2: Using uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Authentication

- `POST /api/auth/register` - Register a new user
- `POST /api/auth/login` - Login user
- `GET /api/auth/me` - Get current user info
- `POST /api/auth/logout` - Logout user

### API Documentation

Once the server is running, you can access:
- Interactive API docs: `http://localhost:8000/docs`
- ReDoc documentation: `http://localhost:8000/redoc`

## Database

The application uses SQLite by default for development. The database file will be created automatically when you first run the application.

For production, update the `DATABASE_URL` to use PostgreSQL:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/izishop
```

## Testing the API

### Register a new user:

```bash
curl -X POST "http://localhost:8000/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "Test123!",
    "confirm_password": "Test123!",
    "first_name": "John",
    "last_name": "Doe",
    "role": "CUSTOMER",
    "phone": "+237123456789"
  }'
```

### Login:

```bash
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "Test123!"
  }'
```

## Frontend Integration

The frontend is configured to connect to this backend API. Make sure the frontend is running on `http://localhost:3000` or update the CORS settings in `main.py` if using a different port. 