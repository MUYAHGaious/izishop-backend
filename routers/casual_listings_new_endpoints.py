# NEW ENDPOINTS TO ADD TO casual_listings.py

# ==================== GET SINGLE LISTING ====================
@router.get("/{listing_id}")
async def get_listing_details(
    listing_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get detailed information about a specific listing"""
    try:
        listing = db.query(CasualListing).filter(CasualListing.id == listing_id).first()

        if not listing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Listing not found"
            )

        # Increment view count
        listing.views_count = (listing.views_count or 0) + 1
        db.commit()

        listing_dict = listing.to_dict()

        # Get seller info
        seller = db.query(User).filter(User.id == listing.seller_id).first()
        if seller:
            listing_dict["seller_name"] = f"{seller.first_name} {seller.last_name}".strip()
            listing_dict["seller_email"] = seller.email

        # Check if current user has favorited this listing
        if current_user:
            is_favorited = db.query(CasualListingFavorite).filter(
                and_(
                    CasualListingFavorite.user_id == current_user.id,
                    CasualListingFavorite.listing_id == listing.id
                )
            ).first() is not None
            listing_dict["is_favorited"] = is_favorited
            listing_dict["is_own_listing"] = (listing.seller_id == current_user.id)
        else:
            listing_dict["is_favorited"] = False
            listing_dict["is_own_listing"] = False

        return {
            "success": True,
            "data": listing_dict
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching listing details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch listing details"
        )


# ==================== CREATE LISTING ====================
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_listing(
    listing_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new casual listing"""
    try:
        # Validate user role
        if current_user.role not in ["CASUAL_SELLER", "SHOP_OWNER"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only casual sellers and shop owners can create listings"
            )

        # Validate required fields
        required_fields = ["title", "description", "price", "condition", "category"]
        missing_fields = [field for field in required_fields if not listing_data.get(field)]
        if missing_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required fields: {', '.join(missing_fields)}"
            )

        # Validate category
        if listing_data["category"] not in MARKETPLACE_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category. Must be one of: {MARKETPLACE_CATEGORIES}"
            )

        # Validate condition
        condition_value = listing_data["condition"].lower().replace(' ', '_')
        if condition_value not in MARKETPLACE_CONDITIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid condition. Must be one of: {MARKETPLACE_CONDITIONS}"
            )

        # Validate price
        try:
            price = float(listing_data["price"])
            if price <= 0:
                raise ValueError("Price must be positive")
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid price value"
            )

        # Create new listing
        new_listing = CasualListing(
            id=str(uuid.uuid4()),
            seller_id=current_user.id,
            title=listing_data["title"].strip(),
            description=listing_data["description"].strip(),
            price=price,
            condition=condition_value,
            category=listing_data["category"],
            location=listing_data.get("location", "").strip(),
            city=listing_data.get("city", "").strip(),
            region=listing_data.get("region", "").strip(),
            is_negotiable=listing_data.get("is_negotiable", False),
            is_delivery_available=listing_data.get("is_delivery_available", False),
            tags=listing_data.get("tags", []),
            images=listing_data.get("images", []),
            status="active",
            seller_type="casual" if current_user.role == "CASUAL_SELLER" else "shop_owner",
            views_count=0,
            favorites_count=0,
            inquiries_count=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        db.add(new_listing)
        db.commit()
        db.refresh(new_listing)

        logger.info(f"Created casual listing: {new_listing.id} by user {current_user.id}")

        return {
            "success": True,
            "message": "Listing created successfully",
            "data": new_listing.to_dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating listing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create listing: {str(e)}"
        )


# ==================== UPDATE LISTING ====================
@router.patch("/{listing_id}")
async def update_listing(
    listing_id: str,
    listing_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a casual listing"""
    try:
        listing = db.query(CasualListing).filter(CasualListing.id == listing_id).first()

        if not listing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Listing not found"
            )

        # Check ownership
        if listing.seller_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own listings"
            )

        # Update allowed fields
        allowed_fields = ["title", "description", "price", "condition", "category",
                         "location", "city", "region", "is_negotiable",
                         "is_delivery_available", "tags", "images", "status"]

        for field, value in listing_data.items():
            if field in allowed_fields and value is not None:
                if field == "condition":
                    value = value.lower().replace(' ', '_')
                    if value not in MARKETPLACE_CONDITIONS:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid condition"
                        )
                elif field == "category":
                    if value not in MARKETPLACE_CATEGORIES:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid category"
                        )
                elif field == "price":
                    value = float(value)
                elif field == "status":
                    if value not in ["active", "sold", "inactive", "deleted"]:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")

                setattr(listing, field, value)

        listing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(listing)

        return {"success": True, "message": "Listing updated successfully", "data": listing.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ==================== DELETE LISTING ====================
@router.delete("/{listing_id}")
async def delete_listing(
    listing_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a casual listing"""
    try:
        listing = db.query(CasualListing).filter(CasualListing.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
        if listing.seller_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own listings")

        listing.status = "deleted"
        listing.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {"success": True, "message": "Listing deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ==================== FAVORITE LISTING ====================
@router.post("/{listing_id}/favorite")
async def toggle_favorite(
    listing_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Toggle favorite status"""
    try:
        listing = db.query(CasualListing).filter(CasualListing.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")

        existing_favorite = db.query(CasualListingFavorite).filter(
            and_(CasualListingFavorite.user_id == current_user.id, CasualListingFavorite.listing_id == listing_id)
        ).first()

        if existing_favorite:
            db.delete(existing_favorite)
            listing.favorites_count = max(0, (listing.favorites_count or 0) - 1)
            db.commit()
            return {"success": True, "message": "Removed from favorites", "is_favorited": False}
        else:
            new_favorite = CasualListingFavorite(
                id=str(uuid.uuid4()), user_id=current_user.id, listing_id=listing_id, created_at=datetime.now(timezone.utc)
            )
            db.add(new_favorite)
            listing.favorites_count = (listing.favorites_count or 0) + 1
            db.commit()
            return {"success": True, "message": "Added to favorites", "is_favorited": True}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ==================== SEND INQUIRY ====================
@router.post("/{listing_id}/inquire")
async def send_inquiry(
    listing_id: str,
    inquiry_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send an inquiry to the seller"""
    try:
        listing = db.query(CasualListing).filter(CasualListing.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
        if listing.seller_id == current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot inquire about your own listing")

        message = inquiry_data.get("message")
        if not message or not message.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required")

        new_inquiry = CasualListingInquiry(
            id=str(uuid.uuid4()), listing_id=listing_id, buyer_id=current_user.id,
            seller_id=listing.seller_id, message=message.strip(), created_at=datetime.now(timezone.utc)
        )
        db.add(new_inquiry)
        listing.inquiries_count = (listing.inquiries_count or 0) + 1
        db.commit()

        return {
            "success": True, "message": "Inquiry sent successfully",
            "data": {"inquiry_id": str(new_inquiry.id), "listing_id": listing_id, "message": message}
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
