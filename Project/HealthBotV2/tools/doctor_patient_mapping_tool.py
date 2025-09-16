#!/usr/bin/env python3
"""
Doctor Patient Mapping Tool for Revival Medical System
"""

import logging
import json
from typing import Optional, Dict, Any
from langchain.tools import BaseTool
from dal.database import DatabaseManager

logger = logging.getLogger(__name__)

class DoctorPatientMappingTool(BaseTool):
    """Tool for getting doctor-patient mapping information with role-based access"""
    name: str = "get_doctor_patient_info"
    description: str = """Get doctor-patient mapping information with role-based access control.
    
    Parameters:
    - query_type (str): Type of query - "my_doctor", "my_dha", "patient_primary_doctor", "patient_dha", "doctor_patients"
    - patient_id (int): Patient ID (optional for patient role, required for staff queries)
    - doctor_id (int): Doctor ID (optional, for specific doctor queries)
    - doctor_name (str): Doctor name (optional, alternative to doctor_id)
    
    Use this tool for queries like:
    - "My doctor details" → query_type="my_doctor" (patient role)
    - "My DHA details" → query_type="my_dha" (patient role)
    - "Primary doctor for patient 123" → query_type="patient_primary_doctor", patient_id=123 (staff role)
    - "DHA details for patient 123" → query_type="patient_dha", patient_id=123 (staff role)
    - "List patients assigned to doctor 1212" → query_type="doctor_patients", doctor_id=1212 (staff role)
    - "Patients assigned to Dr. Smith" → query_type="doctor_patients", doctor_name="Smith" (staff role)
    
    This tool handles all doctor-patient relationship queries and returns detailed information including:
    - Doctor contact information and specialization
    - DHA (Department of Health Authorization) details
    - Patient assignments and primary doctor relationships
    """
    
    def __init__(self):
        super().__init__()
        # Don't set user_context as instance variable to avoid Pydantic validation issues
    
    def set_user_context(self, user_context):
        """Set user context for role-based access control"""
        # Use object.__setattr__ to bypass Pydantic validation
        object.__setattr__(self, 'user_context', user_context)
    
    def _run(self, query_type: str, patient_id: Optional[int] = None, 
             doctor_id: Optional[int] = None, doctor_name: Optional[str] = None) -> str:
        """Execute the doctor-patient mapping query with role-based access control"""
        logger.info(f"🔍 DoctorPatientMappingTool._run called with query_type={query_type}, patient_id={patient_id}, doctor_id={doctor_id}, doctor_name={doctor_name}")
        user_context = getattr(self, 'user_context', None)
        logger.info(f"🔍 User context: {user_context}")
        
        try:
            # Enforce role-based access control
            if user_context and user_context.get('role_id') == 1:  # Patient role
                # Patients can only query their own information
                patient_id = user_context.get('user_id')
                logger.info(f"Patient access: restricting query to patient ID {patient_id}")
                
                # Only allow patient-specific queries
                if query_type not in ['my_doctor', 'my_dha']:
                    return json.dumps({
                        "error": "Access denied: Patients can only query 'my_doctor' or 'my_dha' information.",
                        "allowed_queries": ["my_doctor", "my_dha"]
                    }, indent=2)
            
            elif not user_context or user_context.get('role_id') != 1:  # Medical staff
                # Medical staff can query any patient information
                if query_type in ['my_doctor', 'my_dha']:
                    return json.dumps({
                        "error": "Invalid query type for medical staff. Use 'patient_primary_doctor', 'patient_dha', or 'doctor_patients'.",
                        "allowed_queries": ["patient_primary_doctor", "patient_dha", "doctor_patients"]
                    }, indent=2)
                
                # For staff queries, patient_id or doctor_id must be provided
                if query_type in ['patient_primary_doctor', 'patient_dha'] and not patient_id:
                    return json.dumps({
                        "error": "patient_id is required for patient-specific queries"
                    }, indent=2)
                
                if query_type == 'doctor_patients' and not doctor_id and not doctor_name:
                    return json.dumps({
                        "error": "doctor_id or doctor_name is required for doctor patient queries"
                    }, indent=2)
            
            with DatabaseManager() as db_manager:
                if query_type == "my_doctor" or query_type == "patient_primary_doctor":
                    # First try to get primary doctor
                    primary_doctor = db_manager.get_primary_doctor(patient_id=patient_id)
                    
                    if primary_doctor:
                        # Get additional doctor details from users table
                        doctor_user = db_manager.get_users(user_id=primary_doctor['user_id'])
                        doctor_details = doctor_user[0] if doctor_user else None
                        
                        result = {
                            "patient_id": patient_id,
                            "primary_doctor": {
                                "doctor_id": primary_doctor['user_id'],
                                "doctor_name": primary_doctor['doctor_name'],
                                "doctor_email": primary_doctor['doctor_email'],
                                "doctor_role_id": primary_doctor['doctor_role_id'],
                                "is_primary": primary_doctor['is_primary'],
                                "assignment_from": primary_doctor['from_date'],
                                "assignment_to": primary_doctor['to_date'],
                                "is_active": primary_doctor['is_active']
                            }
                        }
                        
                        if doctor_details:
                            result["primary_doctor"].update({
                                "mobile_number": doctor_details.mobile_number,
                                "qualification": getattr(doctor_details, 'qualification', None),
                            })
                    else:
                        # No primary doctor found, get all assigned doctors
                        all_doctors = db_manager.get_patient_doctors(patient_id=patient_id)
                        
                        if not all_doctors:
                            return json.dumps({
                                "message": f"No doctors assigned to patient {patient_id}",
                                "patient_id": patient_id,
                                "assigned_doctors": []
                            }, indent=2)
                        
                        result = {
                            "patient_id": patient_id,
                            "message": "No primary doctor assigned, showing all assigned doctors",
                            "assigned_doctors": all_doctors,
                            "total_doctors": len(all_doctors)
                        }
                    
                    return json.dumps(result, indent=2)
                
                elif query_type == "my_dha" or query_type == "patient_dha":
                    # Get all doctors (including DHA) for the patient
                    patient_doctors = db_manager.get_patient_doctors(patient_id=patient_id, active_only=True)
                    
                    if not patient_doctors:
                        return json.dumps({
                            "message": f"No doctors/DHA found for patient {patient_id}",
                            "patient_id": patient_id,
                            "doctors": [],
                            "dha_details": []
                        }, indent=2)
                    
                    # Get detailed information for each doctor
                    detailed_doctors = []
                    dha_details = []
                    
                    for doctor in patient_doctors:
                        doctor_user = db_manager.get_users(user_id=doctor['user_id'])
                        if doctor_user:
                            doctor_info = {
                                "doctor_id": doctor['user_id'],
                                "doctor_name": doctor['doctor_name'],
                                "doctor_email": doctor['doctor_email'],
                                "mobile_number": doctor_user[0].mobile_number,
                                "role_id": doctor['doctor_role_id'],
                                "is_primary": doctor['is_primary'],
                                "assignment_from": doctor['from_date'],
                                "assignment_to": doctor['to_date'],
                                "is_active": doctor['is_active'],
                                "qualification": getattr(doctor_user[0], 'qualification', None),
                                "specialization": getattr(doctor_user[0], 'specialization', None),
                                "hospital_name": getattr(doctor_user[0], 'hospital_name', None)
                            }
                            
                            detailed_doctors.append(doctor_info)
                            
                            # Check if this is DHA (Department of Health Authorization)
                            # Assuming DHA has specific role_id or specialization
                            if (doctor_info.get('specialization') and 
                                'dha' in doctor_info['specialization'].lower()) or \
                               (doctor_info.get('qualification') and 
                                'dha' in doctor_info['qualification'].lower()):
                                dha_details.append(doctor_info)
                    
                    return json.dumps({
                        "patient_id": patient_id,
                        "total_doctors": len(detailed_doctors),
                        "doctors": detailed_doctors,
                        "dha_details": dha_details,
                        "message": f"Found {len(detailed_doctors)} doctors for patient {patient_id}" + 
                                  (f", including {len(dha_details)} DHA personnel" if dha_details else "")
                    }, indent=2)
                
                elif query_type == "doctor_patients":
                    # Get patients assigned to a specific doctor
                    target_doctor_id = doctor_id
                    
                    # If doctor_name provided, find the doctor_id
                    if doctor_name and not doctor_id:
                        doctors = db_manager.get_users()
                        matching_doctors = [d for d in doctors if doctor_name.lower() in d.name.lower()]
                        
                        if not matching_doctors:
                            return json.dumps({
                                "error": f"No doctor found with name containing '{doctor_name}'",
                                "suggestion": "Try using exact doctor name or doctor ID"
                            }, indent=2)
                        
                        if len(matching_doctors) > 1:
                            return json.dumps({
                                "error": f"Multiple doctors found with name containing '{doctor_name}'",
                                "matching_doctors": [{"id": d.id, "name": d.name, "email": d.email} for d in matching_doctors],
                                "suggestion": "Please specify exact doctor ID or more specific name"
                            }, indent=2)
                        
                        target_doctor_id = matching_doctors[0].id
                    
                    if not target_doctor_id:
                        return json.dumps({
                            "error": "Could not determine doctor ID"
                        }, indent=2)
                    
                    # Get doctor details
                    doctor_users = db_manager.get_users(user_id=target_doctor_id)
                    if not doctor_users:
                        return json.dumps({
                            "error": f"Doctor with ID {target_doctor_id} not found"
                        }, indent=2)
                    
                    doctor_info = doctor_users[0]
                    
                    # Get patients assigned to this doctor
                    assigned_patients = db_manager.get_doctor_patients(doctor_user_id=target_doctor_id, active_only=True)
                    
                    # Get detailed patient information
                    detailed_patients = []
                    for patient in assigned_patients:
                        patient_user = db_manager.get_users(user_id=patient['patient_id'])
                        if patient_user:
                            patient_info = {
                                "patient_id": patient['patient_id'],
                                "patient_name": patient['patient_name'],
                                "patient_email": patient['patient_email'],
                                "mobile_number": patient_user[0].mobile_number,
                                "is_primary_assignment": patient['is_primary'],
                                "assignment_from": patient['from_date'],
                                "assignment_to": patient['to_date'],
                                "is_active": patient['is_active']
                            }
                            detailed_patients.append(patient_info)
                    
                    return json.dumps({
                        "doctor": {
                            "doctor_id": target_doctor_id,
                            "doctor_name": doctor_info.name,
                            "doctor_email": doctor_info.email,
                            "mobile_number": doctor_info.mobile_number,
                            "qualification": getattr(doctor_info, 'qualification', None),
                            "specialization": getattr(doctor_info, 'specialization', None)
                        },
                        "total_patients": len(detailed_patients),
                        "patients": detailed_patients,
                        "message": f"Doctor {doctor_info.name} has {len(detailed_patients)} assigned patients"
                    }, indent=2)
                
                else:
                    return json.dumps({
                        "error": f"Invalid query_type: {query_type}",
                        "valid_types": ["my_doctor", "my_dha", "patient_primary_doctor", "patient_dha", "doctor_patients"]
                    }, indent=2)
        
        except Exception as e:
            logger.error(f"Error in DoctorPatientMappingTool: {e}")
            return json.dumps({
                "error": f"Database error: {str(e)}",
                "query_type": query_type
            }, indent=2)
    
    async def _arun(self, query_type: str, patient_id: Optional[int] = None, 
                    doctor_id: Optional[int] = None, doctor_name: Optional[str] = None) -> str:
        """Async version of the run method"""
        return self._run(query_type, patient_id, doctor_id, doctor_name)
