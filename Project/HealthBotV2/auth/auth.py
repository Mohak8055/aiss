#!/usr/bin/env python3
"""
Database Token Authentication and Authorization utilities for Revival Medical System
Uses tokens stored in the database instead of JWT
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from dal.database import DatabaseManager
from dal.models.users import Users
from dal.models.role import Role

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer()

class UserContext(BaseModel):
    """User context for authorization"""
    user_id: int
    role_id: int
    role_name: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    token: str
    can_access_all_patients: bool = False

def get_user_by_token(token: str) -> Optional[Users]:
    """Get user from database by token"""
    try:
        with DatabaseManager() as db_manager:
            if not db_manager.db:
                logger.error("Database connection failed")
                return None
            
            # Query user by token
            user = db_manager.db.query(Users).filter(
                Users.token == token,
                Users.status == 1  # Active users only
            ).first()
            
            return user
            
    except Exception as e:
        logger.error(f"Error getting user by token: {e}")
        return None

def get_role_name(role_id: int) -> str:
    """Get role name from role ID"""
    role_mapping = {
        Role.PATIENT: "Patient",
        Role.DOCTOR: "Doctor",
        Role.HEALTH_COACH: "Health Coach",
        Role.ADMIN: "Admin",
        Role.DIAGNOSTIC: "Diagnostic",
        Role.VIDEO_UPLOADER: "Video Uploader",
        Role.TRAINER: "Trainer",
        Role.TRACKER: "Tracker",
        Role.CRM_ADMIN: "CRM Admin",
        Role.CRM_EXECUTIVE: "CRM Executive",
        Role.VENDOR: "Vendor",
        Role.ORDER_MANAGER: "Order Manager",
        Role.VIDEO_ADMIN: "Video Admin",
        Role.READ_ONLY: "Read Only"
    }
    return role_mapping.get(role_id, "Unknown")

def determine_access_level(role_id: int) -> bool:
    """Determine if role can access all patients"""
    # Roles that can access all patient data
    privileged_roles = [
        Role.DOCTOR,
        Role.HEALTH_COACH,
        Role.ADMIN,
        Role.DIAGNOSTIC,
        Role.CRM_ADMIN,
        Role.CRM_EXECUTIVE
    ]
    
    return role_id in privileged_roles

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserContext:
    """Get current authenticated user with role-based access control using database token"""
    try:
        # Extract token from Authorization header
        token = credentials.credentials
        
        if not token:
            raise HTTPException(status_code=401, detail="Token is required")
        
        # Get user from database by token
        user = get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token or user not found")
        
        # Determine access level
        can_access_all = determine_access_level(user.role_id)
        role_name = get_role_name(user.role_id)
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        
        return UserContext(
            user_id=user.id,
            role_id=user.role_id,
            role_name=role_name,
            email=user.email,
            full_name=full_name,
            token=token,
            can_access_all_patients=can_access_all
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_current_user: {e}")
        raise HTTPException(status_code=500, detail="Authentication error")

def require_patient_access(requested_patient_id: Optional[int], current_user: UserContext) -> bool:
    """Check if current user can access requested patient data"""
    try:
        # If user can access all patients, allow access
        if current_user.can_access_all_patients:
            return True
        
        # If user is a patient, they can only access their own data
        if current_user.role_id == Role.PATIENT:
            if requested_patient_id is None:
                # If no specific patient requested, default to current user
                return True
            elif requested_patient_id == current_user.user_id:
                # Patient accessing their own data
                return True
            else:
                # Patient trying to access another patient's data
                raise HTTPException(
                    status_code=403, 
                    detail="Patients can only access their own medical data"
                )
        
        # Default deny for any other scenario
        raise HTTPException(status_code=403, detail="Access denied")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in require_patient_access: {e}")
        raise HTTPException(status_code=500, detail="Authorization error")

def get_authorized_patient_id(requested_patient_id: Optional[int], current_user: UserContext) -> int:
    """Get the authorized patient ID based on user role and request"""
    try:
        # If user can access all patients and a specific patient is requested
        if current_user.can_access_all_patients and requested_patient_id:
            return requested_patient_id
        
        # If user can access all patients but no specific patient requested, return None to indicate "all patients"
        elif current_user.can_access_all_patients and not requested_patient_id:
            return None
        
        # If user is a patient, always return their own ID
        elif current_user.role_id == Role.PATIENT:
            return current_user.user_id
        
        # Default fallback
        else:
            raise HTTPException(status_code=403, detail="Cannot determine authorized patient access")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_authorized_patient_id: {e}")
        raise HTTPException(status_code=500, detail="Authorization error")

# Role-based decorators
def require_roles(*allowed_roles):
    """Decorator to require specific roles"""
    def decorator(func):
        async def wrapper(*args, current_user: UserContext = Depends(get_current_user), **kwargs):
            if current_user.role_id not in allowed_roles:
                role_names = [str(role) for role in allowed_roles]
                raise HTTPException(
                    status_code=403, 
                    detail=f"Access denied. Required roles: {', '.join(role_names)}"
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

def require_admin(current_user: UserContext = Depends(get_current_user)) -> UserContext:
    """Require admin role"""
    if current_user.role_id != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

def require_medical_staff(current_user: UserContext = Depends(get_current_user)) -> UserContext:
    """Require medical staff roles (Doctor, Health Coach, Diagnostic)"""
    medical_roles = [Role.DOCTOR, Role.HEALTH_COACH, Role.DIAGNOSTIC]
    if current_user.role_id not in medical_roles:
        raise HTTPException(status_code=403, detail="Medical staff access required")
    return current_user
