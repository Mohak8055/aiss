#!/usr/bin/env python3
"""
Food log service using Foodlog model (columns: type, url, activitydate, createdon, description).
Adds optional filters meal_type and exact_date (YYYY-MM-DD or natural language handled in tool).
Preserves old behavior when new params are omitted.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from dal.models.users import Users
from dal.models.foodlog import Foodlog

logger = logging.getLogger(__name__)

class FoodlogService:
    def __init__(self, db: Session):
        self.db = db

    def get_foodlog(
        self,
        patient_identifier: Optional[str] = None,
        date_filter: Optional[str] = None,
        limit: int = 10,
        meal_type: Optional[str] = None,
        exact_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return food log entries for a patient with optional filtering."""
        q = self.db.query(Foodlog)

        # Patient filtering (by id or name via join)
        if patient_identifier:
            trimmed = str(patient_identifier).strip()
            if trimmed.isdigit():
                try:
                    pid = int(trimmed)
                    q = q.filter(Foodlog.patient_id == pid)
                except ValueError:
                    q = q.join(Users, Users.id == Foodlog.patient_id).filter(Users.name.ilike(f"%{trimmed}%"))
            else:
                q = q.join(Users, Users.id == Foodlog.patient_id).filter(Users.name.ilike(f"%{trimmed}%"))

        # Meal type filter (Foodlog.type)
        if meal_type:
            q = q.filter(Foodlog.type.ilike(meal_type.strip()))

        # Exact date filter: prefer activitydate string, else compare createdon date part
        if exact_date:
            s = str(exact_date).strip()
            try:
                d = datetime.strptime(s, "%Y-%m-%d").date()
                start_dt = datetime.combine(d, datetime.min.time())
                end_dt = datetime.combine(d, datetime.max.time())
                q = q.filter(
                    or_(
                        Foodlog.activitydate == d.strftime("%Y-%m-%d"),
                        and_(Foodlog.createdon >= start_dt, Foodlog.createdon <= end_dt)
                    )
                )
            except ValueError:
                # If not ISO, compare against activitydate string directly
                q = q.filter(or_(Foodlog.activitydate == s, Foodlog.activitydate.ilike(f"%{s}%")))

        # On/after date filter
        if date_filter:
            try:
                d = datetime.strptime(date_filter, "%Y-%m-%d").date()
                q = q.filter(or_(Foodlog.createdon >= d, Foodlog.activitydate >= d.strftime("%Y-%m-%d")))
            except ValueError:
                logger.warning("Invalid date_filter '%s' passed to get_foodlog; ignoring", date_filter)

        # Ordering: newest first
        try:
            q = q.order_by(Foodlog.createdon.desc())
        except Exception:
            q = q.order_by(Foodlog.id.desc())

        rows = q.limit(limit).all()

        def to_dict(r: Foodlog) -> Dict[str, Any]:
            created = None
            try:
                created = r.createdon.strftime("%Y-%m-%d %H:%M:%S") if r.createdon else None
            except Exception:
                created = None
            return {
                # generic keys used by tools + raw fields for safety
                "entry_datetime": created or (r.activitydate or ""),
                "activitydate": r.activitydate,
                "food_type": getattr(r, "type", None),
                "description": getattr(r, "description", None),
                "image_url": getattr(r, "url", None),
                "url": getattr(r, "url", None),
                "patient_id": getattr(r, "patient_id", None),
            }

        return [to_dict(r) for r in rows]
