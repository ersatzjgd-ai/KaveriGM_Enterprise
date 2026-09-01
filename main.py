import os
from taipy.gui import Gui
from db import fetch_all_guests, start_realtime_listener
from config import PORT

# 1. Global App State Shared Baseline (Updated dynamically via realtime broadcast)
global_guests_df = fetch_all_guests()

# 2. Import Sub-Pages
from manager import manager_md
from team import team_md

# 3. Setup Routing mapping
pages = {
    "/": "<|navbar|>\n# Welcome to KaveriGM\nNavigate to [/manager](/manager) or [/team](/team)",
    "manager": manager_md,
    "team": team_md
}

if __name__ == "__main__":
    gui = Gui(pages=pages)
    
    # Fire up the background WebSockets listener to sync the DB directly to all connected Taipy GUIs
    start_realtime_listener(gui)
    
    # Run the server. Binds to 0.0.0.0 and the dynamic Railway Port
    # use_reloader=False prevents the daemon threads from spawning twice in dev mode
    gui.run(
        host="0.0.0.0", 
        port=PORT, 
        use_reloader=False, 
        title="KaveriGM Enterprise",
        # Ensures websockets are activated for Taipy's internal state sync mechanisms
        client_server_communication="websocket"
    )
