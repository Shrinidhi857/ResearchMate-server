import os
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import WebSocket

class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    HUGGINGFACE = "huggingface"

class Config:
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 8000))
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", LLMProvider.OLLAMA)
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")
    MAX_COMPILATION_ATTEMPTS = int(os.getenv("MAX_COMPILATION_ATTEMPTS", 20))
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

class MessageType(str, Enum):
    CODE_GENERATED = "CODE_GENERATED"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    EXECUTION_SUCCESS = "EXECUTION_SUCCESS"
    USER_MESSAGE = "USER_MESSAGE"
    AGENT_THINKING = "AGENT_THINKING"
    MAX_ATTEMPTS_REACHED = "MAX_ATTEMPTS_REACHED"
    COMPILATION_COMPLETE = "COMPILATION_COMPLETE"
    SAVE_TO_PAPER = "SAVE_TO_PAPER"

class AgentState:
    def __init__(self):
        self.messages: List[Dict[str, Any]] = []
        self.current_code: Optional[str] = None
        self.compilation_attempts: int = 0
        self.max_attempts: int = Config.MAX_COMPILATION_ATTEMPTS
        self.waiting_for_compilation: bool = False
        
    def add_message(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def reset_for_new_request(self):
        self.compilation_attempts = 0
        self.waiting_for_compilation = False

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.agent_states: Dict[str, AgentState] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.agent_states[client_id] = AgentState()
    
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.agent_states:
            del self.agent_states[client_id]
    
    async def send_message(self, client_id: str, message: dict):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)
    
    def get_state(self, client_id: str) -> Optional[AgentState]:
        return self.agent_states.get(client_id)
