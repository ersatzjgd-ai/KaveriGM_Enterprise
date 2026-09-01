from config import MANAGER_PASSWORD
from db import bulk_add_guests, update_guest
from pdf_gen import generate_daily_report
import pandas as pd

# State variables for Manager
manager_input_pwd = ""
is_authenticated = False
bulk_names = ""
selected_lounge = "reception"
lounge_options = ["L1", "L2", "L3", "L4", "L5", "BR", "GMR"]
report_path = ""

def login(state):
    if state.manager_input_pwd == MANAGER_PASSWORD:
        state.is_authenticated = True
    else:
        state.is_authenticated = False

def handle_bulk_add(state):
    names = state.bulk_names.split('\n')
    bulk_add_guests(names)
    state.bulk_names = "" # Clear text area

def activate_guest(state, id, payload):
    # Payload contains row data from Taipy table action
    guest_id = payload["args"][0]
    update_guest(guest_id, {"is_active": True, "lounge": state.selected_lounge})

def undo_activation(state, id, payload):
    guest_id = payload["args"][0]
    update_guest(guest_id, {"is_active": False, "lounge": "reception"})

def download_report(state):
    # Generates PDF based on the global dataframe
    state.report_path = generate_daily_report(state.global_guests_df)

manager_md = """
# KaveriGM **Manager Portal**

<|layout|columns=1 1|
<|
## Authentication
<|{manager_input_pwd}|input|password=True|label=Manager Password|>
<|Login|button|on_action=login|>
|>
|>

<|part|render={is_authenticated}|
---
<|layout|columns=1 2|
<|
## Bulk Add Guests
<|{bulk_names}|input|multiline=True|label=One name per line|class_name=full-width|>
<|Add Guests|button|on_action=handle_bulk_add|>

## Generate Report
<|Generate Daily PDF|button|on_action=download_report|>
<|{report_path}|file_download|label=Download PDF|render={report_path != ""}|>
|>

<|
## Incoming Guests (Awaiting Check-in)
Assign to: <|{selected_lounge}|selector|lov={lounge_options}|dropdown=True|>
<|{global_guests_df[global_guests_df['is_active'] == False]}|table|columns=guest_name,created_at|on_action=activate_guest|action_column=Activate|>

## Active Guests on Floor
<|{global_guests_df[(global_guests_df['is_active'] == True) & (global_guests_df['jai_gurudev'] == False)]}|table|columns=guest_name,lounge,lmw_status,demo_status,met_gurudev|on_action=undo_activation|action_column=Undo|>
|>
|>
|>
"""
