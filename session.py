"""
Session management for storing conversation context.
Stores entity references and conversation history per user session.
"""

from typing import Optional, Dict, List, Any
from datetime import datetime

class SessionManager:
    def __init__(self):
        # In-memory storage: session_id -> session_data
        self.sessions: Dict[str, Dict[str, Any]] = {}
    
    def create_session(self, session_id: str) -> Dict[str, Any]:
        """Create a new session."""
        self.sessions[session_id] = {
            "created_at": datetime.now().isoformat(),
            "current_entity_id": None,
            "current_entity_name": None,
            "conversation_history": [],
            "visited_entities": [],
        }
        return self.sessions[session_id]
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get existing session or create if doesn't exist."""
        if session_id not in self.sessions:
            return self.create_session(session_id)
        return self.sessions[session_id]
    
    def set_current_entity(self, session_id: str, entity_id: str, entity_name: str):
        """Store the current entity being discussed in this session."""
        session = self.get_session(session_id)
        session["current_entity_id"] = entity_id
        session["current_entity_name"] = entity_name
        if entity_id not in session["visited_entities"]:
            session["visited_entities"].append(entity_id)
    
    def get_current_entity(self, session_id: str) -> Optional[Dict[str, str]]:
        """Get the current entity in this session (for follow-up questions)."""
        session = self.get_session(session_id)
        if session["current_entity_id"]:
            return {
                "id": session["current_entity_id"],
                "name": session["current_entity_name"]
            }
        return None
    
    def add_message(self, session_id: str, role: str, content: str):
        """Add message to conversation history."""
        session = self.get_session(session_id)
        session["conversation_history"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_conversation_history(self, session_id: str) -> List[Dict[str, str]]:
        """Get conversation history for this session."""
        session = self.get_session(session_id)
        return session["conversation_history"]
    
    def clear_session(self, session_id: str):
        """Clear a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]


# Global session manager instance
session_manager = SessionManager()
