import os
import base64
import time
import requests
import threading
import numpy as np
import cv2
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client
from fpdf import FPDF
from taipy.gui import Gui, State, notify, get_state_id, invoke_callback

# ==========================================
# 1. ENVIRONMENT SETUP & CONFIGURATION
# ==========================================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID", "")
MANAGER_PASSWORD = os.getenv("MANAGER_PASSWORD", "kaveri_admin")
PORT = int(os.environ.get("PORT", 8080))

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. DOMAIN LOGIC & MAPPINGS
# ==========================================
ZONES_DB_TO_UI = {
    "reception": "Unassigned", 
    "lounge1": "L1", 
    "lounge2": "L2", 
    "lounge3": "L3", 
    "lounge4": "L4", 
    "lounge5": "L5", 
    "br": "BR", 
    "gmr": "GMR", 
    "passageway_top": "Top Hallway",
    "passageway_right_a": "Right Hallway A", 
    "passageway_right_b": "Right Hallway B",
    None: "Unassigned", 
    "": "Unassigned"
}

ZONES_UI_TO_DB = {v: k for k, v in ZONES_DB_TO_UI.items() if k not in [None, ""]}
ZONES_UI_TO_DB["Unassigned"] = "reception"

UI_OPTIONS = ["Unassigned", "L1", "L2", "L3", "L4", "L5", "BR", "GMR"]
SESSION_OPTIONS = ["VIP", "General", "Group", "Special Session"]
STATUS_OPTIONS = ["Not yet", "Started", "Done"]

# Table Column Configurations
incoming_table_cols = {
    "guest_name": {"title": "Name"}, 
    "session_type": {"title": "Session"}, 
    "lounge_ui": {"title": "Lounge"}
}

active_table_cols = {
    "guest_name": {"title": "Name"}, 
    "lounge_ui": {"title": "Lounge"}, 
    "lmw_status": {"title": "LMW"}, 
    "demo_status": {"title": "Demo"}
}

# ==========================================
# 3. TAIPY STATE VARIABLES
# ==========================================
current_role = "On-Ground Team 🏃"
roles = ["On-Ground Team 🏃", "Manager 👔"]

# Manager Portal State
manager_password_input = ""
is_manager_authenticated = False
new_guest_name = ""
new_guest_session = "General"
incoming_guests = pd.DataFrame(columns=['guest_name', 'session_type', 'lounge_ui'])
selected_incoming_index = -1
checkin_guest_name = "Select a guest to check-in"
checkin_guest_id = ""
checkin_lounge = "Unassigned"
camera_image = ""
qr_data = ""
pdf_path = ""

# On-Ground Team Portal State
active_guests = pd.DataFrame(columns=['guest_name', 'lounge_ui', 'lmw_status', 'demo_status'])
selected_lounge_filter = "All"
search_query = ""
filter_options = ["All"] + UI_OPTIONS
selected_active_index = -1
active_guest_name = "Select a guest to manage"
active_guest_id = ""
active_lmw = "Not yet"
active_demo = "Not yet"
active_ready = False
active_met = False
active_lounge = "Unassigned"

# ==========================================
# 4. DATABASE & EXTERNAL API HELPERS
# ==========================================
def fetch_guests():
    """Fetches and categorizes today's guests from Supabase."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    response = supabase.table('guests').select('*').gte('created_at', today).execute()
    
    df = pd.DataFrame(response.data)
    if df.empty:
        empty_inc = pd.DataFrame(columns=['guest_name', 'session_type', 'lounge_ui'])
        empty_act = pd.DataFrame(columns=['guest_name', 'lounge_ui', 'lmw_status', 'demo_status'])
        return empty_inc, empty_act
    
    df['is_active'] = df['is_active'].fillna(False)
    df['has_left_kaveri'] = df['has_left_kaveri'].fillna(False)
    df['jai_gurudev'] = df['jai_gurudev'].fillna(False)
    df['lounge_ui'] = df['lounge'].map(ZONES_DB_TO_UI).fillna("Unassigned")
    
    incoming = df[(df['is_active'] == False) & (df['has_left_kaveri'] == False)].reset_index(drop=True)
    active = df[(df['is_active'] == True) & (df['jai_gurudev'] == False)].reset_index(drop=True)
    
    return incoming, active

def send_telegram_alert(guest_name, guest_id, lounge_ui, photo_path_or_b64=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_GROUP_ID:
        return
    url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    keyboard = {
        "inline_keyboard": [
            [{"text": "L1", "callback_data": f"lng:{guest_id}:lounge1"}, {"text": "L2", "callback_data": f"lng:{guest_id}:lounge2"}, {"text": "L3", "callback_data": f"lng:{guest_id}:lounge3"}, {"text": "L4", "callback_data": f"lng:{guest_id}:lounge4"}],
            [{"text": "L5", "callback_data": f"lng:{guest_id}:lounge5"}, {"text": "BR", "callback_data": f"lng:{guest_id}:br"}, {"text": "GMR", "callback_data": f"lng:{guest_id}:gmr"}]
        ]
    }
    caption = f"🚨 <b>New Arrival</b>\n👤 <b>{guest_name}</b>\n📍 Lounge: <b>{lounge_ui}</b>\n\nPlease assign a lounge:"
    try:
        if photo_path_or_b64:
            if os.path.exists(photo_path_or_b64):
                with open(photo_path_or_b64, "rb") as f:
                    requests.post(f"{url_base}/sendPhoto", data={"chat_id": TELEGRAM_GROUP_ID, "caption": caption, "parse_mode": "HTML", "reply_markup": str(keyboard)}, files={"photo": ("guest.jpg", f, "image/jpeg")})
            else:
                photo_bytes = base64.b64decode(photo_path_or_b64.split(",")[1] if "," in photo_path_or_b64 else photo_path_or_b64)
                requests.post(f"{url_base}/sendPhoto", data={"chat_id": TELEGRAM_GROUP_ID, "caption": caption, "parse_mode": "HTML", "reply_markup": str(keyboard)}, files={"photo": ("guest.jpg", photo_bytes, "image/jpeg")})
        else:
            requests.post(f"{url_base}/sendMessage", json={"chat_id": TELEGRAM_GROUP_ID, "text": caption, "parse_mode": "HTML", "reply_markup": keyboard})
    except Exception as e:
        print(f"Telegram Error: {e}")

# ==========================================
# 5. TAIPY EVENT CALLBACKS & SYNC LOGIC
# ==========================================
def silent_refresh(state):
    """Fetches data and syncs the UI silently without triggering notifications."""
    inc, act = fetch_guests()
    
    # Apply filters
    if state.selected_lounge_filter != "All":
        act = act[act['lounge_ui'] == state.selected_lounge_filter]
    if state.search_query.strip():
        act = act[act['guest_name'].str.contains(state.search_query.strip(), case=False, na=False)]
    
    state.incoming_guests = inc.reset_index(drop=True)
    state.active_guests = act.reset_index(drop=True)

    # Sync the open guest card fields with the database instantly
    if state.active_guest_id:
        current_guest = act[act['id'].astype(str) == state.active_guest_id]
        if not current_guest.empty:
            row = current_guest.iloc[0]
            state.active_lmw = row.get('lmw_status', 'Not yet')
            state.active_demo = row.get('demo_status', 'Not yet')
            state.active_ready = bool(row.get('ready_to_meet_gurudev', False))
            state.active_met = bool(row.get('met_gurudev', False))
            state.active_lounge = row.get('lounge_ui', 'Unassigned')
        else:
            # Guest was completed/deleted from DB manually
            state.active_guest_id = ""
            state.active_guest_name = "Select a guest to manage"

def auto_refresh_loop(state_id):
    """Background thread that triggers a silent UI refresh every 8 seconds."""
    while True:
        time.sleep(8)
        try:
            # Pushes updates from the background thread to the specific user's Taipy session
            invoke_callback(gui, state_id, silent_refresh)
        except Exception:
            pass # Fails gracefully if user disconnects

def on_init(state):
    inc, act = fetch_guests()
    state.incoming_guests = inc
    state.active_guests = act
    
    # Start the auto-refresh background thread for this client session
    state_id = get_state_id(state)
    threading.Thread(target=auto_refresh_loop, args=(state_id,), daemon=True).start()

def refresh_data(state):
    silent_refresh(state)
    notify(state, "info", "Dashboard refreshed.")

def login_manager(state):
    if state.manager_password_input == MANAGER_PASSWORD:
        state.is_manager_authenticated = True
        notify(state, "success", "Logged in successfully!")
    else:
        notify(state, "error", "Invalid Manager Password")

def add_new_guest(state):
    if not state.new_guest_name:
        notify(state, "error", "Guest name is required.")
        return
    data = {"guest_name": state.new_guest_name, "session_type": state.new_guest_session, "is_active": False, "has_left_kaveri": False, "jai_gurudev": False, "lounge": "reception"}
    supabase.table('guests').insert(data).execute()
    notify(state, "success", f"Added {state.new_guest_name}!")
    state.new_guest_name = ""
    refresh_data(state)

def select_incoming(state, id, payload):
    index = payload["index"]
    if index < len(state.incoming_guests):
        row = state.incoming_guests.iloc[index]
        state.selected_incoming_index = index
        state.checkin_guest_id = str(row['id']) if 'id' in row else ""
        state.checkin_guest_name = row['guest_name']
        state.checkin_lounge = "Unassigned"

def scan_qr(state):
    if not state.camera_image:
        notify(state, "error", "No image selected.")
        return
    try:
        img = cv2.imread(state.camera_image) if os.path.exists(state.camera_image) else cv2.imdecode(np.frombuffer(base64.b64decode(state.camera_image.split(",")[1]), np.uint8), cv2.IMREAD_COLOR)
        data, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
        if data:
            state.qr_data = data
            notify(state, "success", f"QR Scanned: {data}")
        else:
            notify(state, "warning", "No QR code detected.")
    except Exception as e:
        notify(state, "error", f"QR Scan failed: {e}")

def check_in_guest(state):
    if not state.checkin_guest_id:
        notify(state, "warning", "Select a guest first.")
        return
    db_lounge = ZONES_UI_TO_DB.get(state.checkin_lounge, "reception")
    update_data = {"is_active": True, "lounge": db_lounge}
    
    if state.camera_image:
        update_data["photo_data"] = base64.b64encode(open(state.camera_image, "rb").read()).decode('utf-8') if os.path.exists(state.camera_image) else state.camera_image

    supabase.table('guests').update(update_data).eq('id', state.checkin_guest_id).execute()
    send_telegram_alert(state.checkin_guest_name, state.checkin_guest_id, state.checkin_lounge, state.camera_image)
    notify(state, "success", f"{state.checkin_guest_name} checked in!")
    state.checkin_guest_name = "Select a guest to check-in"
    state.checkin_guest_id = ""
    state.camera_image = ""
    refresh_data(state)

def generate_pdf(state):
    _, act = fetch_guests()
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Kaveri GM - Daily Report ({datetime.now().strftime('%Y-%m-%d')})", ln=True, align='C')
    for _, row in act.iterrows():
        pdf.cell(200, 10, txt=f"Name: {row['guest_name']} | Lounge: {row['lounge_ui']} | LMW: {row.get('lmw_status', 'Not yet')} | Demo: {row.get('demo_status', 'Not yet')} | Met: {row.get('met_gurudev', False)}", ln=True)
    pdf.output("daily_report.pdf")
    state.pdf_path = "daily_report.pdf"
    notify(state, "success", "PDF Generated! Click download.")

def select_active(state, id, payload):
    index = payload["index"]
    if index < len(state.active_guests):
        row = state.active_guests.iloc[index]
        state.active_guest_id = str(row['id']) if 'id' in row else ""
        state.active_guest_name = row['guest_name']
        state.active_lmw = row.get('lmw_status', 'Not yet')
        state.active_demo = row.get('demo_status', 'Not yet')
        state.active_ready = bool(row.get('ready_to_meet_gurudev', False))
        state.active_met = bool(row.get('met_gurudev', False))
        state.active_lounge = row.get('lounge_ui', 'Unassigned')

def save_active_updates(state):
    if not state.active_guest_id:
        notify(state, "warning", "No guest selected to update.")
        return
    db_lounge = ZONES_UI_TO_DB.get(state.active_lounge, "reception")
    data = {"lmw_status": state.active_lmw, "demo_status": state.active_demo, "ready_to_meet_gurudev": state.active_ready, "met_gurudev": state.active_met, "lounge": db_lounge}
    supabase.table('guests').update(data).eq('id', state.active_guest_id).execute()
    notify(state, "success", "Status updated!")
    refresh_data(state)

def complete_visit(state):
    if not state.active_guest_id:
        notify(state, "warning", "No guest selected.")
        return
    supabase.table('guests').update({"jai_gurudev": True}).eq('id', state.active_guest_id).execute()
    notify(state, "info", "Visit completed.")
    state.active_guest_name = "Select a guest to manage"
    state.active_guest_id = ""
    refresh_data(state)

def generate_wa_link(state):
    if not state.active_guest_name or state.active_guest_name == "Select a guest to manage":
        notify(state, "warning", "Select a guest first.")
        return
    msg = f"Status Update: {state.active_guest_name}\nLounge: {state.active_lounge}\nLMW: {state.active_lmw}\nDemo: {state.active_demo}"
    notify(state, "info", f"https://wa.me/?text={requests.utils.quote(msg)}")

# ==========================================
# 6. TAIPY GUI MARKDOWN LAYOUT
# ==========================================
page_layout = """
# 🏛️ Kaveri GM

<|{current_role}|selector|lov={roles}|>

<|part|render={current_role == "Manager 👔"}|
## Manager Portal

<|part|render={not is_manager_authenticated}|
<|{manager_password_input}|input|password=True|label=Admin Password|>
<|Login|button|on_action=login_manager|>
|>

<|part|render={is_manager_authenticated}|
### Add New Guest
<|layout|columns=1 1 1|
<|{new_guest_name}|input|label=Guest Name|>
<|{new_guest_session}|selector|lov={SESSION_OPTIONS}|dropdown=True|label=Session Type|>
<|Add Guest|button|on_action=add_new_guest|>
|>

<hr/>

### Incoming Guests
*(Click a row to check-in)*
<|{incoming_guests}|table|columns={incoming_table_cols}|on_action=select_incoming|>

#### Check-in selected: **<|{checkin_guest_name}|text|>**
<|layout|columns=1 1|
<|part|
<|{camera_image}|file_selector|label=Upload / Take Photo|extensions=.jpg,.png,.jpeg|>
<|{camera_image}|image|height=200px|>
|>
<|part|
<|Scan QR (from camera)|button|on_action=scan_qr|>
<|{qr_data}|text|>
<br/>
<|{checkin_lounge}|selector|lov={UI_OPTIONS}|dropdown=True|label=Assign Lounge|>
<|Check In & Alert Team|button|on_action=check_in_guest|>
|>
|>

<hr/>

### End of Day
<|Generate Report|button|on_action=generate_pdf|>
<|{pdf_path}|file_download|label=Download PDF|>
|>
|>

<|part|render={current_role == "On-Ground Team 🏃"}|
## On-Ground Portal

<|Refresh Dashboard|button|on_action=refresh_data|>
<br/>

<|{selected_lounge_filter}|toggle|lov={filter_options}|on_change=refresh_data|>

<br/>
<|{search_query}|input|label=🔍 Search Guest Name...|on_change=refresh_data|width=100%|>
<br/>

*(Click a row below to open their management card)*
<|{active_guests}|table|columns={active_table_cols}|on_action=select_active|>

<hr/>

<|part|render={active_guest_id != ""}|
### 👤 <|{active_guest_name}|text|>

<|layout|columns=1 1|
<|{active_lounge}|selector|lov={UI_OPTIONS}|dropdown=True|label=Lounge|>
<|📸 Photo|button|>
|>

<br/>
<|layout|columns=1 1|
<|part|
**📺 LMW**
<|{active_lmw}|toggle|lov={STATUS_OPTIONS}|>
|>
<|part|
**💻 IP Demo**
<|{active_demo}|toggle|lov={STATUS_OPTIONS}|>
|>
|>

<br/>
<|layout|columns=1 1|
<|{active_ready}|toggle|label=⏳ Ready for Vyas|>
<|{active_met}|toggle|label=🤝 Met Gurudev|>
|>

<br/>
<|layout|columns=1 1 1|
<|📱 WhatsApp|button|on_action=generate_wa_link|>
<|💾 Save Updates|button|on_action=save_active_updates|>
<|✅ Complete|button|on_action=complete_visit|>
|>
|>

|>
"""

# ==========================================
# 7. APP ENTRY POINT
# ==========================================
if __name__ == "__main__":
    gui = Gui(page=page_layout)
    gui.run(
        host="0.0.0.0",
        port=PORT,
        dark_mode=True, 
        title="Kaveri GM"
    )
