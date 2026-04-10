import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
import uuid
import json

class DatabaseManager:
    """
    Supabase/PostgreSQL connection and CRUD logic for Socratic Oracle sessions.
    """
    def __init__(self):
        # expects SUPABASE_DB_URL in format: postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT].supabase.co:5432/postgres
        self.db_url = os.getenv("SUPABASE_DB_URL")
        if not self.db_url:
            print("WARNING: SUPABASE_DB_URL is not set.")
        
        self.init_db()

    def get_connection(self):
        return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)

    def init_db(self):
        """Create necessary tables if they don't exist."""
        if not self.db_url:
            return

        create_tables_sql = """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id UUID PRIMARY KEY,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            pdf_context TEXT,
            pdf_metadata JSONB DEFAULT '{}'::jsonb
        );

        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            session_id UUID REFERENCES sessions(session_id) ON DELETE CASCADE,
            role VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS vision_logs (
            id SERIAL PRIMARY KEY,
            session_id UUID REFERENCES sessions(session_id) ON DELETE CASCADE,
            image_prompt TEXT,
            response TEXT,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_tables_sql)
                conn.commit()
            print("Database initialized successfully.")
        except Exception as e:
            print(f"Error initializing DB: {e}")

    # --- Session CRUD ---
    def create_session(self, pdf_context: str, pdf_metadata: dict) -> str:
        session_id = str(uuid.uuid4())
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO sessions (session_id, pdf_context, pdf_metadata) VALUES (%s, %s, %s)",
                        (session_id, pdf_context, json.dumps(pdf_metadata))
                    )
                conn.commit()
            return session_id
        except Exception as e:
            print(f"Error creating session: {e}")
            return session_id

    def get_session(self, session_id: str) -> dict:
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM sessions WHERE session_id = %s", (session_id,))
                    session = cur.fetchone()
                    
                    if session:
                        # Update last active
                        cur.execute("UPDATE sessions SET last_active = CURRENT_TIMESTAMP WHERE session_id = %s", (session_id,))
                        conn.commit()
                        
            return session
        except Exception as e:
            print(f"Error fetching session: {e}")
            return None

    def end_session(self, session_id: str) -> bool:
        # We can either delete the session or keep it for logs. 
        # Typically we keep it, but deliverable 2 removed it from memory. Let's just remove it.
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))
                conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting session: {e}")
            return False

    # --- Message / Conversation CRUD ---
    def add_message(self, session_id: str, role: str, content: str):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)",
                        (session_id, role, content)
                    )
                conn.commit()
        except Exception as e:
            print(f"Error adding message: {e}")

    def get_conversation_history(self, session_id: str, limit: int = 10) -> list:
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get last N messages
                    cur.execute(
                        "SELECT role, content, timestamp FROM messages WHERE session_id = %s ORDER BY timestamp DESC LIMIT %s",
                        (session_id, limit)
                    )
                    rows = cur.fetchall()
            
            # reverse to chronological order
            rows.reverse()
            return [{"speaker": row["role"], "text": row["content"], "timestamp": row["timestamp"].isoformat()} for row in rows]
        except Exception as e:
            print(f"Error getting history: {e}")
            return []

    # --- Vision CRUD ---
    def log_vision_critique(self, session_id: str, prompt: str, response: str):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO vision_logs (session_id, image_prompt, response) VALUES (%s, %s, %s)",
                        (session_id, prompt, response)
                    )
                conn.commit()
        except Exception as e:
            print(f"Error logging vision critique: {e}")
