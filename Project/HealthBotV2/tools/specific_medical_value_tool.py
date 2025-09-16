#!/usr/bin/env python3
"""
Specific Medical Value Tool
Tool for getting specific medical values with time/date filters
"""

import logging
import json
from typing import Optional
from datetime import datetime
from langchain.tools import BaseTool

# Import our medical system components
from dal.database import DatabaseManager

logger = logging.getLogger(__name__)

class SpecificMedicalValueTool(BaseTool):
    """Tool for getting specific medical values with time/date filters"""
    name: str = "get_specific_medical_value"
    description: str = """Get specific medical reading values with precise time and date filtering.
    
    Parameters:
    - patient_id (int): Patient ID number (optional if patient_name provided)
    - patient_name (str): Patient name (optional if patient_id provided)
    - reading_type (str): Type of reading - "glucose", "blood_pressure", "spo2", "body_temperature", "hrv", "stress", "sleep", "activity"
    - specific_time (str): Specific time in ISO format "YYYY-MM-DD HH:MM:SS" (optional)
    - date_filter (str): Date in YYYY-MM-DD format for specific dates OR YYYY-MM format for entire months (optional)
    - time_range (str): Time of day - "morning", "afternoon", "evening", "night" (optional)
    - analysis_type (str): "highest", "lowest", "average", "specific" (optional)
      * "highest" - Returns multiple highest values (up to 10)
      * "lowest" - Returns multiple lowest values (up to 10)
      * "specific" - Returns single specific reading
    
    DATE FORMATS:
    - Specific date: "2025-07-16" (July 16th only)  
    - Entire month: "2025-07" (All of July 2025)
    
    Use this for queries like:
    - "What is sugar value of Rayudu at 10 AM 16th July 2025"
    - "What are the highest 5 BP values of patient on specific date"
    - "List the lowest glucose values in July" → date_filter="2025-07" (month format)
    - "Show highest sugar levels this month" → date_filter="2025-08" (month format)
    """
    
    def __init__(self):
        super().__init__()
        # Don't set user_context as instance variable to avoid Pydantic validation issues
    
    def set_user_context(self, user_context):
        """Set user context for role-based access control"""
        # Use object.__setattr__ to bypass Pydantic validation
        object.__setattr__(self, 'user_context', user_context)
    
    def _run(self, patient_id: Optional[int] = None, patient_name: Optional[str] = None,
             reading_type: str = "glucose", specific_time: Optional[str] = None,
             date_filter: Optional[str] = None, time_range: Optional[str] = None,
             analysis_type: str = "specific") -> str:
        """Get specific medical values with advanced filtering - ROLE-BASED ACCESS CONTROL"""
        try:
            # Enforce role-based access control
            user_context = getattr(self, 'user_context', None)
            if user_context and user_context.get('role_id') == 1:  # Patient role
                # Patients can only access their own data
                patient_id = user_context.get('user_id')
                patient_name = None  # Override any patient_name to enforce access control
                logger.info(f"Patient access: restricting query to patient ID {patient_id}")
            elif patient_id is None and patient_name is None:
                # For medical staff, if no patient specified, this might be an error
                return "Please specify a patient ID or patient name for the medical reading query."
            
            with DatabaseManager() as db_manager:
                # Parse datetime inputs
                specific_datetime = None
                date_datetime = None
                month_filter = False  # Initialize month_filter flag
                
                if specific_time:
                    try:
                        specific_datetime = datetime.fromisoformat(specific_time)
                    except ValueError:
                        try:
                            specific_datetime = datetime.strptime(specific_time, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            return f"Error: Invalid specific_time format. Use YYYY-MM-DD HH:MM:SS"
                
                if date_filter:
                    try:
                        # Check if it's a month format (YYYY-MM)
                        if len(date_filter) == 7 and date_filter.count('-') == 1:
                            # Month format: YYYY-MM
                            year, month = date_filter.split('-')
                            date_datetime = datetime(int(year), int(month), 1)
                            # Mark as month filter for service
                            month_filter = True
                        else:
                            # Full date format: YYYY-MM-DD
                            date_datetime = datetime.fromisoformat(date_filter)
                            month_filter = False
                    except ValueError:
                        try:
                            date_datetime = datetime.strptime(date_filter, "%Y-%m-%d")
                            month_filter = False
                        except ValueError:
                            return f"Error: Invalid date_filter format. Use YYYY-MM for months or YYYY-MM-DD for specific dates"
                
                # Get specific readings using existing method
                result = db_manager.get_specific_reading_value(
                    patient_id=patient_id,
                    patient_name=patient_name,
                    reading_type=reading_type,
                    specific_time=specific_datetime,
                    date_filter=date_datetime,
                    time_range=time_range,
                    analysis_type=analysis_type,
                    limit=10,  # Get up to 10 readings for highest/lowest
                    month_filter=month_filter
                )
                
                if "error" in result:
                    return f"Error: {result['error']}"
                
                # Special handling for sleep data - return aggregated results directly
                if reading_type == "sleep":
                    if "total_sleep_hours" in result:
                        return json.dumps({
                            "reading_type": "sleep",
                            "patient_id": result["patient_id"],
                            "date_filter": result.get("date_filter"),
                            "total_sleep_records": result.get("total_sleep_records", 0),
                            "total_sleep_hours": result.get("total_sleep_hours", 0),
                            "total_sleep_duration": result.get("total_sleep_duration", "0 hours"),
                            "sleep_breakdown": result.get("sleep_breakdown", {}),
                            "summary": result.get("summary", "No sleep data available"),
                            "individual_readings": result.get("individual_readings", [])
                        }, indent=2)
                    else:
                        return json.dumps({
                            "reading_type": "sleep",
                            "patient_id": result["patient_id"],
                            "message": "No sleep data found for the specified criteria",
                            "readings": result.get("readings", [])
                        }, indent=2)
                
                # Analyze the readings based on analysis_type for non-sleep data
                readings = result.get("readings", [])
                if not readings:
                    return f"No {reading_type} readings found for patient {result.get('patient_id', 'unknown')}."
                
                # Return OPTIMIZED response to prevent token overflow
                if analysis_type == "highest":
                    value_field = "systolic" if reading_type == "blood_pressure" else "value"
                    if reading_type == "body_temperature":
                        value_field = "temperature"
                    
                    # Sort readings by value descending and return top readings
                    sorted_readings = sorted(readings, key=lambda x: x.get(value_field, 0), reverse=True)
                    top_readings = sorted_readings[:min(10, len(sorted_readings))]  # Limit to 10 for readability
                    
                    return json.dumps({
                        "analysis": "highest",
                        "reading_type": reading_type,
                        "patient_id": result["patient_id"],
                        "highest_readings": top_readings,
                        "highest_value": top_readings[0].get(value_field) if top_readings else None,
                        "total_readings_found": len(readings),
                        "showing_top": len(top_readings),
                        "message": f"Showing top {len(top_readings)} highest {reading_type} readings out of {len(readings)} total"
                    }, indent=2)
                
                elif analysis_type == "lowest":
                    value_field = "systolic" if reading_type == "blood_pressure" else "value"
                    if reading_type == "body_temperature":
                        value_field = "temperature"
                    
                    # Sort readings by value ascending and return bottom readings
                    sorted_readings = sorted(readings, key=lambda x: x.get(value_field, float('inf')))
                    bottom_readings = sorted_readings[:min(10, len(sorted_readings))]  # Limit to 10 for readability
                    
                    return json.dumps({
                        "analysis": "lowest",
                        "reading_type": reading_type,
                        "patient_id": result["patient_id"],
                        "lowest_readings": bottom_readings,
                        "lowest_value": bottom_readings[0].get(value_field) if bottom_readings else None,
                        "total_readings_found": len(readings),
                        "showing_bottom": len(bottom_readings),
                        "message": f"Showing bottom {len(bottom_readings)} lowest {reading_type} readings out of {len(readings)} total"
                    }, indent=2)
                
                elif analysis_type == "specific" and specific_datetime:
                    # Find the closest reading to specific time
                    if readings:
                        closest = min(readings, key=lambda x: abs(
                            datetime.fromisoformat(x.get("timestamp", x.get("date", ""))) - specific_datetime
                        ))
                        return json.dumps({
                            "analysis": "specific_time",
                            "reading_type": reading_type,
                            "patient_id": result["patient_id"],
                            "closest_reading": closest,
                            "requested_time": specific_time
                        }, indent=2)
                
                # Default: return latest reading only to save tokens
                latest_reading = readings[0] if readings else None
                return json.dumps({
                    "reading_type": reading_type,
                    "patient_id": result["patient_id"],
                    "latest_reading": latest_reading,
                    "total_readings_found": len(readings),
                    "message": f"Showing latest {reading_type} reading. Total {len(readings)} readings found."
                }, indent=2)
                
        except Exception as e:
            logger.error(f"Error in SpecificMedicalValueTool: {e}")
            return f"Error getting specific medical values: {str(e)}"
