"""
Diagnostic script to test Supabase connection and HKU API independently.
Run locally: python test_connection.py
"""
import os
import sys
import json

# Load .env file manually
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                if val and val != "your_groq_api_key_here":
                    os.environ.setdefault(key.strip(), val.strip())

print("=" * 60)
print("SOCRATIC ORACLE - CONNECTION DIAGNOSTIC")
print("=" * 60)

# --- Test 1: Environment Variables ---
print("\n📋 TEST 1: Environment Variables")
hku_key = os.getenv("HKU_API_KEY")
db_url = os.getenv("SUPABASE_DB_URL")

if hku_key:
    print(f"  ✅ HKU_API_KEY = {hku_key[:8]}...{hku_key[-4:]}")
else:
    print("  ❌ HKU_API_KEY is NOT SET")

if db_url:
    # Mask the password
    safe_url = db_url
    if "@" in db_url and ":" in db_url:
        safe_url = db_url.split("@")[0][:30] + "...@" + db_url.split("@")[1]
    print(f"  ✅ SUPABASE_DB_URL = {safe_url[:60]}...")
else:
    print("  ❌ SUPABASE_DB_URL is NOT SET")
    print("  💡 Set it in your .env file or Render dashboard")

# --- Test 2: Supabase DB Connection ---
print("\n📋 TEST 2: Supabase Database Connection")
if db_url:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        # Ensure sslmode
        if "sslmode" not in db_url:
            sep = "&" if "?" in db_url else "?"
            db_url += f"{sep}sslmode=require"
        
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor, connect_timeout=10)
        cur = conn.cursor()
        
        # Check if tables exist
        cur.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name IN ('sessions', 'messages', 'vision_logs')
            ORDER BY table_name;
        """)
        tables = [row["table_name"] for row in cur.fetchall()]
        
        if "sessions" in tables:
            print(f"  ✅ 'sessions' table exists")
            cur.execute("SELECT COUNT(*) as cnt FROM sessions")
            print(f"     → {cur.fetchone()['cnt']} sessions stored")
        else:
            print(f"  ❌ 'sessions' table MISSING — run the SQL below")
            
        if "messages" in tables:
            print(f"  ✅ 'messages' table exists")
            cur.execute("SELECT COUNT(*) as cnt FROM messages")
            print(f"     → {cur.fetchone()['cnt']} messages stored")
        else:
            print(f"  ❌ 'messages' table MISSING — run the SQL below")
            
        if "vision_logs" in tables:
            print(f"  ✅ 'vision_logs' table exists")
        else:
            print(f"  ⚠️  'vision_logs' table missing (optional for Deliverable 3)")
        
        # Check columns match what the code expects
        cur.execute("""
            SELECT column_name, data_type FROM information_schema.columns 
            WHERE table_name = 'sessions' ORDER BY ordinal_position;
        """)
        cols = [row["column_name"] for row in cur.fetchall()]
        expected = {"session_id", "created_at", "last_active", "pdf_context", "pdf_metadata"}
        missing = expected - set(cols)
        if missing:
            print(f"  ❌ 'sessions' table is missing columns: {missing}")
        else:
            print(f"  ✅ 'sessions' schema matches code expectations")
            
        cur.execute("""
            SELECT column_name, data_type FROM information_schema.columns 
            WHERE table_name = 'messages' ORDER BY ordinal_position;
        """)
        cols = [row["column_name"] for row in cur.fetchall()]
        expected = {"id", "session_id", "role", "content", "timestamp"}
        missing = expected - set(cols)
        if missing:
            print(f"  ❌ 'messages' table is missing columns: {missing}")
        else:
            print(f"  ✅ 'messages' schema matches code expectations")
        
        conn.close()
        print(f"  ✅ Connection closed cleanly")
        
    except Exception as e:
        print(f"  ❌ Connection FAILED: {e}")
else:
    print("  ⏭️  Skipped (no SUPABASE_DB_URL)")

# --- Test 3: HKU API ---
print("\n📋 TEST 3: HKU LLM API")
if hku_key:
    try:
        import httpx
        
        url = "https://api.hku.hk/openai/deployments/gpt-4.1-nano/chat/completions?api-version=2025-04-01-preview"
        headers = {"Content-Type": "application/json", "api-key": hku_key}
        payload = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant. Reply in one sentence."},
                {"role": "user", "content": "Say hello."}
            ],
            "temperature": 0.7
        }
        
        print(f"  📡 Calling {url[:50]}...")
        resp = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        
        if resp.status_code == 200:
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
            print(f"  ✅ API responded: \"{reply[:80]}\"")
        else:
            print(f"  ❌ API returned HTTP {resp.status_code}")
            print(f"     Body: {resp.text[:300]}")
            
    except Exception as e:
        print(f"  ❌ API call FAILED: {e}")
else:
    print("  ⏭️  Skipped (no HKU_API_KEY)")

# --- Summary ---
print("\n" + "=" * 60)
print("If any tests failed, fix the issue and re-run this script.")
print("For missing tables, run the SQL in your Supabase SQL Editor:")
print("  → See: supabase_setup.sql")
print("=" * 60)
