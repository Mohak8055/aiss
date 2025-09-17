"""
Medical LangChain Agent for Revival Hospital System
"""

import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta

try:
    from langchain.agents import create_openai_tools_agent, AgentExecutor
    from langchain_community.chat_models import ChatOllama
    from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain.schema import HumanMessage, AIMessage
    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    LANGCHAIN_AVAILABLE = False
    print(f"LangChain not available: {e}")

# Import medical tools
try:
    from tools import (
        SpecificMedicalValueTool,
        MultiPatientAnalysisTool,
        SimpleMedicalAnalysisTool,
        HospitalDocumentSearchTool,
        MedicationsTool,
        FoodlogTool,
        ProtocolTool,
        PlanTool,
        DoctorPatientMappingTool,
        UserProfileTool,
        DeviceTool
    )
    TOOLS_AVAILABLE = True
except ImportError as e:
    TOOLS_AVAILABLE = False
    print(f"Medical tools not available: {e}")

logger = logging.getLogger(__name__)

class MedicalLangChainAgent:
    """
    LangChain-based medical agent with conversation memory
    """

    def __init__(self, openai_api_key: str):
        """Initialize LangChain medical agent with tools and conversation tracking"""
        self.openai_api_key = openai_api_key
        self.agent_executor = None
        self.conversation_history = []  # Simple list to track conversations
        self.tools = []
        self.user_context = None  # Store user context for role-based access

        if LANGCHAIN_AVAILABLE:
            self._setup_langchain_agent()

    def _generate_date_context(self) -> str:
        """Generate dynamic date context for the agent prompt"""
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        last_month = now.replace(day=1) - timedelta(days=1)
        
        return f"""**CURRENT DATE CONTEXT - CRITICAL:**
   - Today's date is {now.strftime('%B %d, %Y')}
   - "this month" → "{now.strftime('%Y-%m')}"
   - "today" → "{now.strftime('%Y-%m-%d')}"
   - "yesterday" → "{yesterday.strftime('%Y-%m-%d')}"
   - "last month" → "{last_month.strftime('%Y-%m')}"
   - Always use {now.year} as the current year unless explicitly specified otherwise."""

    def _setup_langchain_agent(self):
        """Setup LangChain agent with medical tools and memory"""
        try:
            llm = ChatOllama(model="llama3", temperature=0.1)
            self.tools = self._create_medical_tools()
            current_date_context = self._generate_date_context()

            role_instructions = ""
            if self.user_context:
                if self.user_context.get('role_id') == 1:  # Patient role
                    role_instructions = """
🔒 **PATIENT ACCESS MODE**
- You are assisting a patient with their personal medical records.
- All medical queries are about the patient's own data unless another patient is explicitly mentioned by name.
- If another patient's name is mentioned, respond with: "I can only access your personal medical records."
"""
                else:  # Medical staff
                    role_instructions = f"""
👩‍⚕️ **MEDICAL STAFF ACCESS MODE**
- You are assisting: {self.user_context.get('role_name')} (User ID: {self.user_context.get('user_id')}).
- You have access to all patient data as authorized medical personnel.
"""
            
            patient_db_info = """
🏥 **PATIENT DATABASE:**
- Patient 111: Eswar Umamaheshwar
- Patient 132: Rayudu Dhananjaya  
- Patient 156: Rahul Mark
"""

            prompt = ChatPromptTemplate.from_messages([
                ("system", f"""You are a medical assistant AI for Revival Hospital.

{role_instructions}
{patient_db_info}

**AVAILABLE TOOLS:**
- `get_specific_medical_value`: For specific medical readings like glucose, blood_pressure, etc.
- `analyze_multiple_patients`: To analyze readings across multiple patients.
- `get_medications`: For medication and supplement information.
- `get_foodlog`: For food log entries. This can include images.
- `get_protocols`: For treatment protocols and guidelines.
- `get_my_plan`: For patient plan details.
- `get_doctor_patient_info`: For doctor-patient mapping information.
- `get_user_profile`: For user profile information.
- `check_device_status`: To check the status of medical devices.
- `search_hospital_documents`: For general hospital-related questions and documents.

{current_date_context}
"""),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad")
            ])
            
            agent = create_openai_tools_agent(llm, self.tools, prompt)
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                verbose=True,
                max_iterations=5,
                handle_parsing_errors=True,
                return_intermediate_steps=False,
                max_execution_time=120
            )
            logger.info("✅ Medical LangChain agent initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to setup medical LangChain agent: {e}")
            self.agent_executor = None

    def set_user_context(self, user_context: Dict[str, Any]):
        """Set user context for role-based access control"""
        self.user_context = user_context
        logger.info(f"User context set for agent: User {user_context.get('user_id')} (Role: {user_context.get('role_name')})")
        if LANGCHAIN_AVAILABLE:
            self.tools = self._create_medical_tools()
            self._setup_langchain_agent()

    def _create_medical_tools(self) -> List:
        """Create medical tools for LangChain agent with user context"""
        try:
            if not TOOLS_AVAILABLE:
                return []
            
            tools = [
                SpecificMedicalValueTool(),
                MultiPatientAnalysisTool(),
                SimpleMedicalAnalysisTool(),
                HospitalDocumentSearchTool(),
                MedicationsTool(),
                FoodlogTool(),
                ProtocolTool(),
                PlanTool(),
                DoctorPatientMappingTool(),
                UserProfileTool(),
                DeviceTool()
            ]

            for tool in tools:
                if hasattr(tool, 'set_user_context'):
                    tool.set_user_context(self.user_context)
            
            return tools
        except Exception as e:
            logger.error(f"❌ Failed to create medical tools: {e}")
            return []

    async def chat(self, message: str) -> Dict[str, Any]:
        """Process a chat message with automatic tool selection and memory"""
        try:
            if not (self.agent_executor and LANGCHAIN_AVAILABLE):
                return {"message": "Medical agent not available.", "metadata": {"error": True}}

            self.conversation_history.append({"role": "user", "content": message})
            
            # Truncate conversation history to manage tokens
            truncated_history = self.truncate_conversation_history(
                self.conversation_history[:-1],  # Exclude current message
                12000,  # max tokens
                20      # max messages
            )

            chat_history = [
                HumanMessage(content=msg["content"]) if msg["role"] == "user" else AIMessage(content=msg["content"])
                for msg in truncated_history
            ]
            
            response = await self.agent_executor.ainvoke({
                "input": message,
                "chat_history": chat_history
            })

            if response.get("output"):
                self.conversation_history.append({"role": "assistant", "content": response["output"]})
            
            return {
                "message": response.get("output", ""),
                "metadata": {
                    "agent_type": "Revival365AI Agent",
                    "memory_messages": len(self.conversation_history),
                    "timestamp": datetime.now().isoformat(),
                    "tools_available": len(self.tools),
                    "response_length": len(response.get("output", ""))
                }
            }
        except Exception as e:
            logger.error(f"Medical chat processing failed: {e}")
            return {"message": f"An error occurred: {e}", "metadata": {"error": True}}

    def truncate_conversation_history(self, conversation_history: List[Dict[str, Any]], 
                                    max_tokens: int = 12000,
                                    max_messages: int = 20) -> List[Dict[str, Any]]:
        """Truncate conversation history to stay within token limits"""
        if not conversation_history:
            return []
        
        # First, limit by number of messages
        if len(conversation_history) > max_messages:
            conversation_history = conversation_history[-max_messages:]
        
        # Simple token estimation (4 chars per token)
        total_chars = 0
        truncated_history = []
        
        # Start from most recent and work backwards
        for msg in reversed(conversation_history):
            msg_chars = len(msg.get("content", ""))
            if total_chars + msg_chars > max_tokens * 4:  # rough estimation
                break
            total_chars += msg_chars
            truncated_history.insert(0, msg)
        
        return truncated_history

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get conversation history"""
        return self.conversation_history.copy()

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history.clear()