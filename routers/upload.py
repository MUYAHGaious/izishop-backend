import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
import shutil
from PIL import Image
import logging
from typing import List

from database.connection import get_db
from routers.auth import get_current_user
from schemas.user import UserResponse
from models.user import UserRole
from services.shop import get_shop_by_owner_id, update_shop
from schemas.shop import ShopUpdate

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Constants
UPLOAD_DIR = Path("uploads")
SHOP_IMAGES_DIR = UPLOAD_DIR / "shop_images"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Create upload directories
UPLOAD_DIR.mkdir(exist_ok=True)
SHOP_IMAGES_DIR.mkdir(exist_ok=True)

def validate_image_file(file: UploadFile) -> None:
    """Validate uploaded image file"""
    # Check file size
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size too large. Maximum size allowed is {MAX_FILE_SIZE // (1024*1024)}MB"
        )
    
    # Check file extension
    if file.filename:
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
            )
    
    # Check MIME type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid content type. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
        )

def process_and_save_image(file: UploadFile, image_type: str, shop_id: str) -> str:
    """Process and save uploaded image"""
    try:
        # Generate unique filename
        file_ext = Path(file.filename).suffix.lower() if file.filename else ".jpg"
        filename = f"{shop_id}_{image_type}_{uuid.uuid4().hex}{file_ext}"
        file_path = SHOP_IMAGES_DIR / filename
        
        # Save uploaded file temporarily
        temp_path = SHOP_IMAGES_DIR / f"temp_{filename}"
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Process image with PIL
        with Image.open(temp_path) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Resize based on image type
            if image_type == "profile":
                # Square crop for profile photos
                size = min(img.size)
                left = (img.width - size) // 2
                top = (img.height - size) // 2
                img = img.crop((left, top, left + size, top + size))
                img = img.resize((400, 400), Image.Resampling.LANCZOS)
            elif image_type == "background":
                # Maintain aspect ratio for background images
                img.thumbnail((1200, 400), Image.Resampling.LANCZOS)
                
                # Create a new image with fixed dimensions and center the thumbnail
                background = Image.new('RGB', (1200, 400), (255, 255, 255))
                x = (1200 - img.width) // 2
                y = (400 - img.height) // 2
                background.paste(img, (x, y))
                img = background
            
            # Save processed image
            img.save(file_path, format='JPEG', quality=85, optimize=True)
        
        # Remove temporary file
        temp_path.unlink()
        
        # Return relative path for URL
        return f"/uploads/shop_images/{filename}"
        
    except Exception as e:
        # Clean up temporary files
        if temp_path.exists():
            temp_path.unlink()
        logger.error(f"Error processing image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process image"
        )

@router.post("/shop/profile-photo")
async def upload_shop_profile_photo(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload shop profile photo"""
    try:
        # Verify user is a shop owner
        if current_user.role != UserRole.SHOP_OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only shop owners can upload shop images"
            )
        
        # Get user's shop
        shop = get_shop_by_owner_id(db=db, owner_id=current_user.id)
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        # Validate file
        validate_image_file(file)
        
        # Process and save image
        image_url = process_and_save_image(file, "profile", shop.id)
        
        # Update shop with new profile photo URL
        shop_update = ShopUpdate(profile_photo=image_url)
        updated_shop = update_shop(db=db, shop_id=shop.id, shop_data=shop_update)
        
        if not updated_shop:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update shop profile photo"
            )
        
        logger.info(f"Shop profile photo updated: {shop.id} by {current_user.email}")
        
        return {
            "message": "Profile photo uploaded successfully",
            "image_url": image_url,
            "shop_id": shop.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading shop profile photo: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload profile photo"
        )

@router.post("/shop/background-image")
async def upload_shop_background_image(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload shop background image"""
    try:
        # Verify user is a shop owner
        if current_user.role != UserRole.SHOP_OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only shop owners can upload shop images"
            )
        
        # Get user's shop
        shop = get_shop_by_owner_id(db=db, owner_id=current_user.id)
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        # Validate file
        validate_image_file(file)
        
        # Process and save image
        image_url = process_and_save_image(file, "background", shop.id)
        
        # Update shop with new background image URL
        shop_update = ShopUpdate(background_image=image_url)
        updated_shop = update_shop(db=db, shop_id=shop.id, shop_data=shop_update)
        
        if not updated_shop:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update shop background image"
            )
        
        logger.info(f"Shop background image updated: {shop.id} by {current_user.email}")
        
        return {
            "message": "Background image uploaded successfully",
            "image_url": image_url,
            "shop_id": shop.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading shop background image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload background image"
        )

@router.get("/shop_images/{filename}")
async def serve_shop_image(filename: str):
    """Serve shop images"""
    file_path = SHOP_IMAGES_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )
    
    return FileResponse(
        path=file_path,
        media_type="image/jpeg",
        filename=filename
    )

@router.delete("/shop/profile-photo")
async def delete_shop_profile_photo(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete shop profile photo"""
    try:
        # Verify user is a shop owner
        if current_user.role != UserRole.SHOP_OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only shop owners can delete shop images"
            )
        
        # Get user's shop
        shop = get_shop_by_owner_id(db=db, owner_id=current_user.id)
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        # Remove profile photo URL from database
        shop_update = ShopUpdate(profile_photo=None)
        updated_shop = update_shop(db=db, shop_id=shop.id, shop_data=shop_update)
        
        if not updated_shop:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete shop profile photo"
            )
        
        logger.info(f"Shop profile photo deleted: {shop.id} by {current_user.email}")
        
        return {"message": "Profile photo deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shop profile photo: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete profile photo"
        )

@router.delete("/shop/background-image")
async def delete_shop_background_image(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete shop background image"""
    try:
        # Verify user is a shop owner
        if current_user.role != UserRole.SHOP_OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only shop owners can delete shop images"
            )
        
        # Get user's shop
        shop = get_shop_by_owner_id(db=db, owner_id=current_user.id)
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        # Remove background image URL from database
        shop_update = ShopUpdate(background_image=None)
        updated_shop = update_shop(db=db, shop_id=shop.id, shop_data=shop_update)
        
        if not updated_shop:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete shop background image"
            )
        
        logger.info(f"Shop background image deleted: {shop.id} by {current_user.email}")
        
        return {"message": "Background image deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shop background image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete background image"
        )