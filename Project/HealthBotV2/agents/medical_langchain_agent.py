"""
Medical LangChain Agent for Revival Hospital System
Deterministic, tool-first answers. No tool names/IDs/URLs in replies.
"""

import logging
import importlib
import pkgutil
from typing import List, Dict, Any, Optional
from datetime import datetime
import os
import re

try:
    from langchain.agents import create_openai_tools_agent, AgentExecutor
    from langchain_community.chat_models import ChatOllama
    from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain.schema import HumanMessage, AIMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

logger = logging.getLogger(__name__)


def _strip_leaks(text: str) -> str:
    """Make responses concise, remove tool/function mentions, IDs, and links."""
    if not isinstance(text, str):
        text = str(text)
    lines = [
        ln for ln in text.splitlines()
        if not re.search(r"^\s*(BOT:|```|Tool:|Observation:|Thought:|Action:|Final Answer:|AgentExecutor)", ln, re.I)
    ]
    s = " ".join(ln.strip() for ln in lines if ln.strip())

    # Remove “according to … tool” or function-y snippets
    s = re.sub(r"\bget_[a-z_]+\([^)]*\)", "", s, flags=re.I)
    s = re.sub(r"\bsearch_[a-z_]+\([^)]*\)", "", s, flags=re.I)
    s = re.sub(r"\bfetch_[a-z_]+\([^)]*\)", "", s, flags=re.I)
    s = re.sub(r"\baccording to [^,.]*\btool\b[^,]*,?\s*", "", s, flags=re.I)
    s = re.sub(r"\busing [^,.]*\btool\b[^:]*:\s*", "", s, flags=re.I)
    s = re.sub(r"\bvia the [^,.]*\btool\b[^,]*,?\s*", "", s, flags=re.I)
    s = re.sub(r"\b(get_foodlog|get_medications|get_medical_readings|get_specific_medical_value)\b", "", s, flags=re.I)

    # Remove URLs and markdown images
    s = re.sub(r"!\[[^\]]*\]\((https?://[^\)]+)\)", "", s)
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"<[^>]+>", "", s)

    # Trim banners/disclaimers
    s = re.sub(r"(Please note|This information is based on).*$", "", s, flags=re.I)
    s = re.sub(r"\s{2,}", " ", s).strip()

    # Keep one concise sentence unless asked for a list/table
    if s.count(". ") >= 1 and not re.search(r"(list|table|show|all|summary|compare|history|trend)", s, re.I):
        s = s.split(". ")[0].rstrip(".") + "."
    return s


class MedicalLangChainAgent:
    """
    Deterministic agent wrapper with strict tool usage for data queries.
    """

    def __init__(self, user_context: Optional[Dict[str, Any]] = None, **kwargs):
        self.user_context = user_context or {}
        self.conversation_history: List[Dict[str, str]] = []
        self.agent_executor: Any = None
        self.tools: List[Any] = []
        self._init_complete = False

    # Back-compat for your chat_routes.py
    def set_user_context(self, ctx: Dict[str, Any]):
        self.user_context = ctx or {}

    async def initialize(self):
        if self._init_complete or not LANGCHAIN_AVAILABLE:
            return
        try:
            # Deterministic LLM: lock temperature, top_p and seed (via model_kwargs)
            seed = int(os.getenv("OLLAMA_SEED", "42"))
            llm = ChatOllama(
                model=os.getenv("OLLAMA_MODEL", "llama3"),
                temperature=0.0,
                top_p=1.0,
                model_kwargs={"seed": seed},
            )

            self.tools = self._create_tools()
            for t in self.tools:
                try:
                    setattr(t, "user_context", self.user_context)
                except Exception:
                    pass

            current_date_context = f"Today is {datetime.now().strftime('%B %d, %Y')}."

            # Very explicit rules to prevent guessing and to force tools
            prompt = ChatPromptTemplate.from_messages([
                ("system", f"""You are a medical assistant AI for Revival Hospital.
                 
                 **CRITICAL INSTRUCTION: You must behave as a deterministic system. For the exact same user input, you must use the exact same tools with the exact same parameters and provide the exact same final answer, regardless of the conversation history.**

ABSOLUTE RULES:
- Be concise: one short sentence unless the user explicitly asks for a list/table.
- Don not make up information or use your general knowledge
- NEVER guess patient data. ALWAYS call appropriate tools for medical data (meals, glucose/vitals, medications, protocols).
- If a tool returns no data, say "No record found for that request." Do not invent details.
- Do NOT mention tools, functions, IDs, databases, or access modes.
- If the question names a patient, include the name naturally (e.g., "Rayudu's ...").
- For meal-on-date questions (e.g., "Rayudu's breakfast on 13 March 2025"), call the food log tool and answer with its result only.
- No URLs, emojis, or disclaimers—just the answer.
                 

{current_date_context}"""),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad"),
            ])

            agent = create_openai_tools_agent(llm, self.tools, prompt)
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                verbose=False,
                max_iterations=5,
                handle_parsing_errors=True,
                return_intermediate_steps=False,
            )
            self._init_complete = True
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            self._init_complete = False

    def _create_tools(self) -> List[Any]:
        tools: List[Any] = []
        if not LANGCHAIN_AVAILABLE:
            return tools
        try:
            import tools as tools_pkg
        except Exception as e:
            logger.error(f"❌ Tools package not importable: {e}")
            return tools

        # Prefer these first so the agent sees them
        preferred = [
            "foodlog_tool",
            "specific_medical_value_tool",
            "medical_readings_tool",
            "medications_tool",
            "protocols_tool",
            "doctor_patient_info_tool",
            "basic_medical_analysis_tool",
        ]
        discovered = [m.name for m in pkgutil.iter_modules(tools_pkg.__path__) if m.name != "__init__"]
        ordered = preferred + [n for n in discovered if n not in preferred]

        for mod_name in ordered:
            try:
                module = importlib.import_module(f"tools.{mod_name}")
            except Exception as e:
                logger.warning(f"Skipping tool '{mod_name}': {e}")
                continue
            for attr in dir(module):
                obj = getattr(module, attr)
                try:
                    from langchain.tools import BaseTool as _BT
                    if isinstance(obj, type) and issubclass(obj, _BT) and obj is not _BT:
                        try:
                            tools.append(obj())
                        except Exception as e:
                            logger.warning(f"Could not instantiate {attr} from {mod_name}: {e}")
                except Exception:
                    continue

        logger.info(f"Loaded {len(tools)} tool(s): {[getattr(t, 'name', '?') for t in tools]}")
        return tools

    async def chat(self, message: str) -> Dict[str, Any]:
        try:
            if not (self.agent_executor and LANGCHAIN_AVAILABLE):
                return {"message": "Medical agent not available.", "metadata": {"error": True}}

            # Keep a short memory window for determinism
            self.conversation_history.append({"role": "user", "content": message})
            chat_history: List[Any] = []
            for msg in self.conversation_history[-20:]:
                chat_history.append(HumanMessage(content=msg["content"]) if msg["role"] == "user"
                                  else AIMessage(content=msg["content"]))

            result = await self.agent_executor.ainvoke({"input": message, "chat_history": chat_history})
            out = result.get("output") or ""

            # Final cleanup: concise + no leaks
            out = _strip_leaks(out)
            if not out:
                out = "No record found for that request."
            self.conversation_history.append({"role": "assistant", "content": out})

            return {
                "message": out,
                "metadata": {
                    "agent": "Revival365AI",
                    "timestamp": datetime.now().isoformat(),
                },
            }
        except Exception as e:
            logger.error(f"Agent chat failed: {e}")
            return {"message": f"An error occurred: {e}", "metadata": {"error": True}}

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        return list(self.conversation_history)

    def clear_history(self):
        self.conversation_history.clear()


# Back-compat alias (your router imports from agents import MedicalLangChainAgent)
MedicalLangchainAgent = MedicalLangChainAgent
