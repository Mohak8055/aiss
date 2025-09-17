from dal.database import get_db_manager
from langchain.tools import BaseTool
from typing import Dict, Any, Optional
from services.user_service import get_user_context

class FoodlogTool(BaseTool):
    name = "get_foodlog"
    description = "Useful for getting food log entries for a patient, with optional date filtering. Always provide patient_identifier unless user is asking about their own data. For example, if the user asks 'what did I eat yesterday', do not provide patient_identifier."
    user_context: Optional[Dict[str, Any]] = None

    def set_user_context(self, user_context: Dict[str, Any]):
        """Set user context for role-based access control"""
        self.user_context = user_context

    def _run(
        self,
        patient_identifier: Optional[str] = None,
        date_filter: Optional[str] = None,
        limit: int = 10
    ) -> str:
        """
        Get food log entries for a patient.
        """
        # If no patient_identifier is provided, check user context (for patient role)
        if not patient_identifier and self.user_context and self.user_context.get('role_id') == 1:
            patient_identifier = str(self.user_context.get('user_id'))

        db_manager = get_db_manager()
        foodlog_entries = db_manager.get_foodlog(
            patient_identifier=patient_identifier,
            date_filter=date_filter,
            limit=limit
        )

        if not foodlog_entries:
            return "No food log entries found."

        response = ""
        for entry in foodlog_entries:
            response += f"Patient: {entry['patient_name']}\n"
            response += f"Date: {entry['entry_datetime']}\n"
            response += f"Type: {entry['food_type']}\n"
            response += f"Description: {entry['description']}\n"
            response += f"Activity: {entry['activity']}\n"
            # Check if an image URL exists and add it to the response
            if entry.get('image_url'):
                response += f"Image URL: {entry['image_url']}\n"
            response += "---\n"

        return response

    async def _arun(
        self,
        patient_identifier: Optional[str] = None,
        date_filter: Optional[str] = None,
        limit: int = 10
    ) -> str:
        """
        Asynchronously get food log entries for a patient.
        """
        return self._run(
            patient_identifier=patient_identifier,
            date_filter=date_filter,
            limit=limit
        )