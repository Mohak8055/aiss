from typing import Dict, Any, Optional, List
from langchain.tools import BaseTool
from dal.database import get_db_manager
from datetime import datetime

class FoodlogTool(BaseTool):
    """
    Retrieve food log entries (concise TEXT ONLY; no links, no images).
    """

    name: str = "get_foodlog"
    description: str = (
        "Get food log entries for a patient. "
        "Params: patient_identifier (id or name), date_filter (YYYY-MM-DD), "
        "exact_date (YYYY-MM-DD or natural-language), meal_type (e.g., 'breakfast'), limit (int). "
        "When exact_date and meal_type are provided, return a single concise sentence (text only)."
    )

    user_context: Dict[str, Any] = {}

    # ---------- helpers ----------
    @staticmethod
    def _normalize_exact_date(exact_date: Optional[str]) -> Optional[str]:
        if not exact_date:
            return exact_date
        s = str(exact_date).strip()
        for suf in ("st", "nd", "rd", "th"):
            s = s.replace(f" {suf} ", " ").replace(suf + " ", " ")
        s = s.replace(",", " ").replace("  ", " ").strip()
        fmts = ["%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"]
        for fmt in fmts:
            try:
                return datetime.strptime(s, fmt).date().strftime("%Y-%m-%d")
            except Exception:
                continue
        try:
            parts = s.split()
            if len(parts) == 3 and parts[0].isdigit():
                return datetime.strptime(f"{int(parts[0])} {parts[1]} {int(parts[2])}", "%d %B %Y").date().strftime("%Y-%m-%d")
        except Exception:
            pass
        return exact_date

    def _resolve_patient_identifier(self, patient_identifier: Optional[str]) -> Optional[str]:
        try:
            if not patient_identifier and isinstance(self.user_context, dict):
                if self.user_context.get("role_id") == 1 and self.user_context.get("user_id"):
                    return str(self.user_context.get("user_id"))
        except Exception:
            pass
        return patient_identifier

    @staticmethod
    def _display_name_from_identifier(patient_identifier: Optional[str]) -> Optional[str]:
        if not patient_identifier:
            return None
        s = str(patient_identifier).strip()
        return None if s.isdigit() else s

    # ---------- formatting (TEXT ONLY) ----------
    def _format_entry_sentence(self, entry: Dict[str, Any], patient_identifier: Optional[str]) -> str:
        dt = entry.get("entry_datetime") or entry.get("activitydate") or ""
        date_part = dt.split(" ")[0] if dt else ""
        desc = entry.get("description") or "No description available"
        meal = (entry.get("food_type") or entry.get("type") or "").capitalize() or "Meal"
        name = self._display_name_from_identifier(patient_identifier)
        who = f"{name}'s " if name else ""
        return f"{who}{meal} on {date_part}: {desc}."

    def _format_entries_block(self, entries: List[Dict[str, Any]], patient_identifier: Optional[str]) -> str:
        if not entries:
            return "No food log entries found."
        name = self._display_name_from_identifier(patient_identifier)
        prefix = f"{name}: " if name else ""
        lines = []
        for e in entries:
            dt = e.get("entry_datetime") or e.get("activitydate") or ""
            meal = (e.get("food_type") or e.get("type") or "").capitalize() or "Meal"
            desc = e.get("description") or "No description available"
            line = f"- {prefix}{meal} @ {dt}: {desc}"
            lines.append(line)
        return "\n".join(lines)

    # ---------- run ----------
    def _run(
        self,
        patient_identifier: Optional[str] = None,
        date_filter: Optional[str] = None,
        limit: int = 10,
        meal_type: Optional[str] = None,
        exact_date: Optional[str] = None,
    ) -> str:
        patient_identifier = self._resolve_patient_identifier(patient_identifier)
        exact_date = self._normalize_exact_date(exact_date)

        db_manager = get_db_manager()
        entries = db_manager.get_foodlog(
            patient_identifier=patient_identifier,
            date_filter=date_filter,
            limit=limit,
            meal_type=meal_type,
            exact_date=exact_date,
        )

        if not entries or (isinstance(entries, dict) and entries.get("error")):
            return "No food log entries found."

        if exact_date and meal_type and isinstance(entries, list) and len(entries) >= 1:
            return self._format_entry_sentence(entries[0], patient_identifier)

        if isinstance(entries, list):
            return self._format_entries_block(entries, patient_identifier)

        return "No food log entries found."

    async def _arun(
        self,
        patient_identifier: Optional[str] = None,
        date_filter: Optional[str] = None,
        limit: int = 10,
        meal_type: Optional[str] = None,
        exact_date: Optional[str] = None,
    ) -> str:
        return self._run(
            patient_identifier=patient_identifier,
            date_filter=date_filter,
            limit=limit,
            meal_type=meal_type,
            exact_date=exact_date,
        )
