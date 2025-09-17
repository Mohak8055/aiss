#!/usr/bin/env python3
"""
Food log service for handling food log and nutrition data
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from dal.models.foodlog import Foodlog
from dal.models.users import Users
from dal.services.base_service import BaseService
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime

class FoodlogService(BaseService):
    def __init__(self, db_session: Session):
        super().__init__(db_session)

    def get_foodlog(self, patient_identifier: Optional[str] = None, date_filter: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        query = self.db_session.query(
            Foodlog.entry_datetime,
            Foodlog.food_type,
            Foodlog.description,
            Foodlog.activity,
            Foodlog.image_url,  # Add this line
            Users.name.label("patient_name")
        ).join(Users, Foodlog.patient_id == Users.id)

        if patient_identifier:
            query = query.filter(Users.name.ilike(f"%{patient_identifier}%"))

        if date_filter:
            try:
                filter_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
                query = query.filter(Foodlog.entry_datetime >= filter_date)
            except ValueError:
                pass  # Handle invalid date format if necessary

        results = query.order_by(Foodlog.entry_datetime.desc()).limit(limit).all()

        return [
            {
                "entry_datetime": result.entry_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                "food_type": result.food_type,
                "description": result.description,
                "activity": result.activity,
                "image_url": result.image_url,  # Add this line
                "patient_name": result.patient_name,
            }
            for result in results
        ]