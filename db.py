import asyncio
import threading
from supabase import create_client, Client
import pandas as pd
from config import SUPABASE_URL, SUPABASE_KEY

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_all_guests():
    """Fetches all guests and returns as a Pandas DataFrame for Taipy rendering."""
    res = supabase.table("guests").select("*").order("created_at", desc=True).execute()
    return pd.DataFrame(res.data)

def bulk_add_guests(names: list):
    data = [{"guest_name": name.strip()} for name in names if name.strip()]
    if data:
        supabase.table("guests").insert(data).execute()

def update_guest(guest_id: str, updates: dict):
    supabase.table("guests").update(updates).eq("id", guest_id).execute()

def start_realtime_listener(gui):
    """
    Background daemon thread to listen to Supabase Realtime Websocket.
    Triggers Taipy's broadcast_update to push state to all active client sessions instantly.
    """
    def listen():
        async def subscribe():
            # Listen to ALL events (INSERT, UPDATE, DELETE) on the 'guests' table
            channel = supabase.channel('guests_db_changes')
            
            def on_change(payload):
                # When data mutates, fetch the new state and broadcast to all users < 50ms
                updated_df = fetch_all_guests()
                try:
                    # Broadcast updates to all connected active Taipy clients globally
                    gui.broadcast_update("global_guests_df", updated_df)
                except Exception as e:
                    print(f"Broadcast failed: {e}")

            channel.on("postgres_changes", 
                       event="*", 
                       schema="public", 
                       table="guests", 
                       callback=on_change).subscribe()
            
            # Keep the async loop alive
            while True:
                await asyncio.sleep(1)

        asyncio.run(subscribe())

    # Run listener in a background thread so it doesn't block the Taipy GUI
    listener_thread = threading.Thread(target=listen, daemon=True)
    listener_thread.start()
