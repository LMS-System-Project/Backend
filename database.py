from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY

_client: Client | None = None
_admin: Client | None = None


def get_supabase_client() -> Client:
    """Returns a cached Supabase client using the anon key (respects RLS)."""
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def get_supabase_admin() -> Client:
    """Returns a cached Supabase client using the service_role key (bypasses RLS)."""
    global _admin
    if _admin is None:
        _admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _admin
