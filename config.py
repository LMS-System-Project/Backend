import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")

# AI & external services
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
JSEARCH_API_KEY: str = os.getenv("JSEARCH_API_KEY", "")

# File storage: "local" (dev) or "r2" (production)
STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")

# Cloudflare R2 (only needed when STORAGE_BACKEND=r2)
R2_ACCOUNT_ID: str = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID: str = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY: str = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME: str = os.getenv("R2_BUCKET_NAME", "")
R2_PUBLIC_URL: str = os.getenv("R2_PUBLIC_URL", "")

# Rate limiting
RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

if not SUPABASE_URL or SUPABASE_URL == "https://your-project-id.supabase.co":
    print("⚠️  WARNING: SUPABASE_URL is not configured. Update your .env file.")

if not SUPABASE_KEY or SUPABASE_KEY == "your-anon-public-key":
    print("⚠️  WARNING: SUPABASE_KEY is not configured. Update your .env file.")
