#!/usr/bin/env python3
"""
Test API endpoint directly without external HTTP client
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient
from main import app

# Create test client
client = TestClient(app)

def test_health():
    """Test health endpoint"""
    print("Testing health endpoint...")
    response = client.get("/api/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.status_code == 200

def test_registration():
    """Test registration endpoint"""
    print("\nTesting registration endpoint...")
    
    registration_data = {
        "first_name": "Test",
        "last_name": "User",
        "email": "test_api@example.com",
        "password": "TestPassword123!",
        "confirm_password": "TestPassword123!", 
        "phone": "+237123456789",
        "role": "SHOP_OWNER"
    }
    
    print(f"Sending data: {registration_data}")
    
    response = client.post("/api/auth/register", json=registration_data)
    
    print(f"Status: {response.status_code}")
    print(f"Headers: {response.headers}")
    print(f"Response: {response.text}")
    
    return response

if __name__ == "__main__":
    try:
        # Test health first
        if test_health():
            print("✓ Health check passed")
        else:
            print("✗ Health check failed")
            
        # Test registration
        reg_response = test_registration()
        
        if reg_response.status_code in [200, 201]:
            print("✓ Registration test passed")
        elif reg_response.status_code == 400:
            print("⚠ Registration failed with validation error (expected if user exists)")
        else:
            print(f"✗ Registration failed with status {reg_response.status_code}")
            
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()