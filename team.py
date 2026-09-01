import base64
from db import update_guest

# State variables for Team
search_query = ""
team_filter_lounge = "All"
lounge_filters = ["All", "L1", "L2", "L3", "L4", "L5", "BR", "GMR"]
status_options = ["Not yet", "Started", "Done"]

# Dialog State
show_dialog = False
selected_guest_id = ""
selected_guest_name = ""
dg_lounge = ""
dg_lmw = ""
dg_demo = ""
dg_ready = False
dg_met = False
dg_photo_path = ""
wa_link = ""

def filter_team_view(df, search, lounge):
    filtered = df[(df['is_active'] == True) & (df['jai_gurudev'] == False)]
    if lounge != "All":
        filtered = filtered[filtered['lounge'] == lounge]
    if search:
        filtered = filtered[filtered['guest_name'].str.contains(search, case=False, na=False)]
    return filtered

def open_guest_dialog(state, id, payload):
    guest_id = payload["args"][0]
    row = state.global_guests_df[state.global_guests_df['id'] == guest_id].iloc[0]
    
    state.selected_guest_id = guest_id
    state.selected_guest_name = row['guest_name']
    state.dg_lounge = row['lounge']
    state.dg_lmw = row['lmw_status']
    state.dg_demo = row['demo_status']
    state.dg_ready = row['ready_to_meet_gurudev']
    state.dg_met = row['met_gurudev']
    
    # Generate WhatsApp Link
    msg = f"Guest {row['guest_name']} is currently at {row['lounge']}. LMW: {row['lmw_status']}."
    state.wa_link = f"https://wa.me/?text={msg.replace(' ', '%20')}"
    
    state.show_dialog = True

def close_dialog(state):
    state.show_dialog = False

def save_guest_updates(state):
    updates = {
        "lounge": state.dg_lounge,
        "lmw_status": state.dg_lmw,
        "demo_status": state.dg_demo,
        "ready_to_meet_gurudev": state.dg_ready,
        "met_gurudev": state.dg_met
    }
    
    # If a new photo was uploaded, convert and save it
    if state.dg_photo_path:
        with open(state.dg_photo_path, "rb") as img_file:
            encoded = base64.b64encode(img_file.read()).decode("utf-8")
            updates["photo_data"] = f"data:image/jpeg;base64,{encoded}"
        state.dg_photo_path = "" # reset
        
    update_guest(state.selected_guest_id, updates)
    state.show_dialog = False

def complete_visit(state):
    update_guest(state.selected_guest_id, {"jai_gurudev": True})
    state.show_dialog = False

team_md = """
# On-Ground **Team Portal**

<|layout|columns=1 3|
<|
Search: <|{search_query}|input|>
|>
<|
Filter Lounge: <|{team_filter_lounge}|toggle|lov={lounge_filters}|>
|>
|>

---

<|{filter_team_view(global_guests_df, search_query, team_filter_lounge)}|table|columns=guest_name,lounge,lmw_status,demo_status|on_action=open_guest_dialog|action_column=Manage|>

<|{show_dialog}|dialog|title=Manage Guest: {selected_guest_name}|width=400px|
**Lounge Location**
<|{dg_lounge}|selector|lov={lounge_filters[1:]}|dropdown=True|>

**LMW Status**
<|{dg_lmw}|toggle|lov={status_options}|>

**Demo Status**
<|{dg_demo}|toggle|lov={status_options}|>

**Gurudev Status**
<|{dg_ready}|toggle|label=Ready for Vyas|>
<|{dg_met}|toggle|label=Met Gurudev|>

**Photo Capture**
<|{dg_photo_path}|file_selector|label=Upload/Capture Photo|extensions=.png,.jpg,.jpeg|>

---
<|Save Updates|button|on_action=save_guest_updates|>
<|Complete Visit (Jai Gurudev)|button|on_action=complete_visit|>
<|Close|button|on_action=close_dialog|>

[Share to WhatsApp]({wa_link})
|>
"""
