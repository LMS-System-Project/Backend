import httpx

# ── Force HTTP/1.1 globally ──────────────────────────────────────────────────
# The supabase Python client uses httpx with http2=True internally.
# Supabase servers intermittently terminate HTTP/2 connections, causing
# CONNECTIONTERMINATED errors. Patching httpx.Client to default to HTTP/1.1.
_original_httpx_init = httpx.Client.__init__

def _patched_httpx_init(self, *args, **kwargs):
    kwargs.setdefault("http2", False)
    _original_httpx_init(self, *args, **kwargs)

httpx.Client.__init__ = _patched_httpx_init
# ─────────────────────────────────────────────────────────────────────────────

from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY


def get_supabase_client() -> Client:
    """Returns a fresh Supabase client using the anon key (respects RLS)."""
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_supabase_admin() -> Client:
    """Returns a fresh Supabase client using the service_role key (bypasses RLS)."""
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)



