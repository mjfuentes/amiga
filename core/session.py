"""
Session management for Telegram bot
Phase 2: Persistent sessions with conversation history
"""

import json
import logging
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Conversation message"""

    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str


@dataclass
class Session:
    """User session with Claude Code"""

    user_id: int
    created_at: str
    last_activity: str
    history: list[Message]
    current_workspace: str | None = None  # Current working repository/workspace

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        # Convert message dicts to Message objects
        history = [Message(**msg) for msg in data.get("history", [])]
        return cls(
            user_id=data["user_id"],
            created_at=data["created_at"],
            last_activity=data["last_activity"],
            history=history,
            current_workspace=data.get("current_workspace"),
        )


class SessionManager:
    """Manages user sessions with persistent storage"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.sessions_file = self.data_dir / "sessions.json"
        self.sessions: dict[int, Session] = {}

        # Load existing sessions
        self._load_sessions()

        logger.info(f"SessionManager initialized with {len(self.sessions)} active sessions")

    def _load_sessions(self):
        """Load sessions from disk"""
        if not self.sessions_file.exists():
            return

        try:
            with open(self.sessions_file) as f:
                data = json.load(f)
                for user_id_str, session_data in data.items():
                    user_id = int(user_id_str)
                    session = Session.from_dict(session_data)
                    self.sessions[user_id] = session

            logger.info(f"Loaded {len(self.sessions)} sessions from disk")
        except Exception as e:
            logger.error(f"Error loading sessions: {e}", exc_info=True)

    def _save_sessions(self):
        """Save sessions to disk"""
        try:
            data = {str(user_id): session.to_dict() for user_id, session in self.sessions.items()}

            with open(self.sessions_file, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving sessions: {e}", exc_info=True)

    def get_session(self, user_id: int) -> Session | None:
        """Get existing session without creating one"""
        return self.sessions.get(user_id)

    def get_or_create_session(self, user_id: int) -> Session:
        """Get existing session or create new one"""
        now = datetime.now().isoformat()

        if user_id not in self.sessions:
            # Create new session
            session = Session(user_id=user_id, created_at=now, last_activity=now, history=[])
            self.sessions[user_id] = session
            self._save_sessions()
            logger.info(f"Created new session for user {user_id}")
        else:
            # Update last activity
            session = self.sessions[user_id]
            session.last_activity = now
            self._save_sessions()

        return self.sessions[user_id]

    def add_message(self, user_id: int, role: str, content: str):
        """Add message to session history"""
        session = self.get_or_create_session(user_id)

        message = Message(role=role, content=content, timestamp=datetime.now().isoformat())

        session.history.append(message)
        session.last_activity = message.timestamp
        self._save_sessions()

        logger.info(f"Added {role} message to session {user_id} (history: {len(session.history)} messages)")

    def get_history(self, user_id: int, limit: int | None = None) -> list[Message]:
        """Get conversation history for user"""
        session = self.get_or_create_session(user_id)

        if limit:
            return session.history[-limit:]
        return session.history

    def clear_session(self, user_id: int):
        """Clear session history"""
        if user_id in self.sessions:
            session = self.sessions[user_id]
            session.history = []
            session.last_activity = datetime.now().isoformat()
            self._save_sessions()
            logger.info(f"Cleared session for user {user_id}")

    def delete_session(self, user_id: int):
        """Delete session completely"""
        if user_id in self.sessions:
            del self.sessions[user_id]
            self._save_sessions()
            logger.info(f"Deleted session for user {user_id}")

    def cleanup_stale_sessions(self):
        """Remove sessions that haven't been active recently - now a no-op since sessions don't timeout"""
        logger.debug("cleanup_stale_sessions called but sessions no longer timeout")
        return 0

    def get_session_stats(self, user_id: int) -> dict:
        """Get statistics about a session"""
        if user_id not in self.sessions:
            return {
                "exists": False,
                "message_count": 0,
                "created_at": None,
                "last_activity": None,
                "current_workspace": None,
            }

        session = self.sessions[user_id]
        return {
            "exists": True,
            "message_count": len(session.history),
            "created_at": session.created_at,
            "last_activity": session.last_activity,
            "user_messages": sum(1 for msg in session.history if msg.role == "user"),
            "assistant_messages": sum(1 for msg in session.history if msg.role == "assistant"),
            "current_workspace": session.current_workspace,
        }

    def set_workspace(self, user_id: int, workspace: str):
        """Set current workspace for user session"""
        session = self.get_or_create_session(user_id)
        session.current_workspace = workspace
        self._save_sessions()
        logger.info(f"Set workspace for user {user_id}: {workspace}")

    def get_workspace(self, user_id: int) -> str | None:
        """Get current workspace for user session"""
        session = self.get_or_create_session(user_id)
        return session.current_workspace


class ClaudeCodeSession:
    """Enhanced Claude Code client with session management"""

    def __init__(self, cli_path: str, workspace: str, session_manager: SessionManager):
        self.cli_path = cli_path
        self.workspace = workspace
        self.session_manager = session_manager

    def _format_conversation_context(self, user_id: int) -> str:
        """Format conversation history as context for Claude"""
        history = self.session_manager.get_history(user_id, limit=10)  # Last 10 messages

        if not history:
            return ""

        # Build context string
        context_parts = ["Previous conversation:"]
        for msg in history:
            prefix = "User" if msg.role == "user" else "Assistant"
            context_parts.append(f"{prefix}: {msg.content}")

        return "\n".join(context_parts) + "\n\nCurrent message:"

    async def send_message(self, user_id: int, message: str) -> str:
        """Send message to Claude Code with conversation context"""
        try:
            # Add user message to history
            self.session_manager.add_message(user_id, "user", message)

            # Get conversation context
            context = self._format_conversation_context(user_id)

            # Prepare full prompt with context
            if context:
                full_prompt = f"{context}\n{message}"
            else:
                full_prompt = message

            # Call Claude Code CLI
            result = subprocess.run(
                [self.cli_path, "-p", "--model", "haiku", full_prompt],
                capture_output=True,
                text=True,
                cwd=self.workspace,
            )

            if result.returncode != 0:
                logger.error(f"Claude CLI error: {result.stderr}", exc_info=True)
                response = f"Error: {result.stderr}"
            else:
                response = result.stdout.strip()

            # Add assistant response to history
            self.session_manager.add_message(user_id, "assistant", response)

            return response
        except Exception as e:
            logger.error(f"Error communicating with Claude: {e}", exc_info=True)
            response = f"Error: {str(e)}"
            self.session_manager.add_message(user_id, "assistant", response)
            return response
