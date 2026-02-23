import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or SUPABASE_URL == "https://your-project-id.supabase.co":
    print("⚠️  WARNING: SUPABASE_URL is not configured. Update your .env file.")

if not SUPABASE_KEY or SUPABASE_KEY == "your-anon-public-key":
    print("⚠️  WARNING: SUPABASE_KEY is not configured. Update your .env file.")
