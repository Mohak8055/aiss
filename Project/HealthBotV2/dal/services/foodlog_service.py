#!/usr/bin/env python3
"""
Food log service for handling food log and nutrition data.

This service exposes a `get_foodlog` method that returns a list of food log
entries for a given patient. It mirrors the upstream implementation but fixes
an important bug: when the caller supplies a numeric patient identifier the
original code would attempt to perform a case‑insensitive name search using
`Users.name.ilike()`.  This caused the database layer to mix up numeric IDs
with names and frequently returned incorrect patient data.  The updated
implementation below inspects the `patient_identifier` parameter and if it
contains only digits it filters directly on the primary key (`Users.id`).  If
the identifier contains any non‑digit characters it falls back to the
original behaviour of performing a `ILIKE` search on the patient name.

The returned entries include the associated image URL so that consumers of
this service can display images alongside other food log information.  If
`date_filter` is supplied the entries are filtered on or after the given
date.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from dal.models.foodlog import Foodlog
from dal.models.users import Users
from dal.services.base_service import BaseService


logger = logging.getLogger(__name__)


class FoodlogService(BaseService):
    """Service class for accessing patient food log data."""

    def __init__(self, db_session: Session):
        super().__init__(db_session)

    def get_foodlog(
        self,
        patient_identifier: Optional[str] = None,
        date_filter: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve food log entries for a patient.

        Parameters
        ----------
        patient_identifier: Optional[str]
            The patient's identifier (either a numeric ID or a name substring).  If
            omitted all patient entries are returned.
        date_filter: Optional[str]
            A date string in ``YYYY‑MM‑DD`` format.  Only entries on or after
            this date will be returned.
        limit: int
            The maximum number of entries to return.  Defaults to 10.

        Returns
        -------
        List[Dict[str, Any]]
            A list of dictionaries containing the food log details.  Each
            dictionary includes the entry timestamp, type, description,
            associated activity, an image URL (if present) and the patient's
            name.
        """
        query = self.db_session.query(
            Foodlog.entry_datetime,
            Foodlog.food_type,
            Foodlog.description,
            Foodlog.activity,
            Foodlog.image_url,
            Users.name.label("patient_name"),
        ).join(Users, Foodlog.patient_id == Users.id)

        # If a patient identifier is supplied, determine whether it's a numeric
        # identifier (patient ID) or a string name.  Numeric IDs should filter
        # directly on the primary key to avoid mixing patient data.
        if patient_identifier:
            trimmed_identifier = patient_identifier.strip()
            if trimmed_identifier.isdigit():
                # Filter by patient ID when the identifier is purely numeric
                try:
                    patient_id = int(trimmed_identifier)
                    query = query.filter(Users.id == patient_id)
                except ValueError:
                    # Fall back to name search if conversion fails
                    query = query.filter(Users.name.ilike(f"%{trimmed_identifier}%"))
            else:
                # Perform case‑insensitive search on the patient name
                query = query.filter(Users.name.ilike(f"%{trimmed_identifier}%"))

        # Apply a date filter if provided.  We allow invalid dates to silently
        # fall through which mirrors the behaviour of the original service.
        if date_filter:
            try:
                filter_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
                query = query.filter(Foodlog.entry_datetime >= filter_date)
            except ValueError:
                logger.warning(
                    "Invalid date_filter '%s' passed to get_foodlog; ignoring",
                    date_filter,
                )

        # Order entries by most recent first and limit the number returned
        results = (
            query.order_by(Foodlog.entry_datetime.desc()).limit(limit).all()
        )

        return [
            {
                "entry_datetime": result.entry_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                "food_type": result.food_type,
                "description": result.description,
                "activity": result.activity,
                "image_url": result.image_url,
                "patient_name": result.patient_name,
            }
            for result in results
        ]