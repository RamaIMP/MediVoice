"""Session-local, fictional appointment tool. Never sends messages or books care."""
from copy import deepcopy

DOCTORS = [
    {"id": "demo-1", "name": "Dr. Asha (Demo)", "clinic": "Demo Green Clinic", "channel": "WhatsApp"},
    {"id": "demo-2", "name": "Dr. Ravi (Demo)", "clinic": "Demo Family Clinic", "channel": "Phone"},
    {"id": "demo-3", "name": "Dr. Meera (Demo)", "clinic": "Demo Care Centre", "channel": "Appointment page"},
]
ACTIONS = ["none", "search", "select", "yes", "decline", "set_date", "set_time",
           "set_patient", "edit_patient", "edit", "cancel"]


def initial_state():
    return dict(stage="closed", selected=None, date="", time="", patient="", notice="", revision=0)


def prompt(state):
    doctor = next((d for d in state.get("doctors", DOCTORS) if d["id"] == state["selected"]), None)
    stage = state["stage"]
    if stage == "closed":
        return "Doctor Connect is closed. We can continue discussing your report."
    if stage == "search":
        if state.get("source") == "location":
            return "Use the controls on screen to share your location or enter your area and city."
        if state.get("source") in ("google", "here"):
            return "I have listed the doctors on screen. Please tap the doctor you want to book."
        if state.get("search_notice"):
            return state["search_notice"] + " Use the on-screen controls to choose a doctor or enter your area and city."
        return "I have listed doctors on screen. Please tap the doctor you want to book."
    if stage == "confirm":
        return f"You selected {doctor['name']}. Please continue using the on-screen controls."
    if stage == "patient_confirm":
        return f"You entered {state['patient']}. Please review the request on screen."
    if stage in ("date", "time", "patient"):
        return {"date": f"You selected {doctor['name']}. Please choose your preferred date on screen.",
                "time": "Please choose your preferred time on screen. This is not a confirmed slot.",
                "patient": "Please enter the patient's name on screen, then tap Review details."}[stage]
    if stage == "review":
        return (f"Your request for {doctor['name']} on {state['date']} at {state['time']} is ready. "
                "Please tap the on-screen button to continue.")
    return (f"Your {doctor['channel']} request preview is ready on screen. "
            "This is a simulated handoff. Nothing has been sent or booked; a real clinic must confirm.")


def transition(current, action, value=""):
    s = deepcopy(current)
    s["notice"] = ""
    value = value.strip()
    if action == "cancel":
        s = initial_state()
    elif action == "search":
        s.update(stage="search", selected=None)
    elif action == "back" and s["stage"] in ("date", "time", "patient", "review", "patient_confirm"):
        s["stage"] = {"date": "search", "time": "date", "patient": "time",
                      "review": "patient", "patient_confirm": "patient"}[s["stage"]]
    elif action in ("select", "select_touch") and s["stage"] != "closed":
        selected = next((d for d in s.get("doctors", DOCTORS) if d["id"] == value), None)
        if selected:
            s.update(selected=value, stage="date" if action == "select_touch" else "confirm")
        else:
            s["notice"] = "Please select one of the three displayed doctors."
    elif action == "yes" and s["stage"] in ("confirm", "patient_confirm", "review"):
        s["stage"] = {"confirm": "date", "patient_confirm": "review", "review": "handoff"}[s["stage"]]
    elif (action == "edit_patient" or action == "decline") and s["stage"] == "patient_confirm":
        s["stage"] = "patient"
    elif action == "decline" and s["stage"] == "confirm":
        s.update(stage="search", selected=None)
    elif action == "edit" and s["stage"] in ("review", "handoff"):
        s["stage"] = "date"
    elif action == "set_patient_touch" and s["stage"] == "patient":
        if value and len(value) <= 100:
            s.update(patient=value, stage="review")
        else:
            s["notice"] = "Please provide a short, non-empty name."
    elif action == f"set_{s['stage']}" and s["stage"] in ("date", "time", "patient"):
        if value and len(value) <= 100:
            s[s["stage"]] = value
            s["stage"] = {"date": "time", "time": "patient", "patient": "patient_confirm"}[s["stage"]]
        else:
            s["notice"] = "Please provide a short, non-empty answer."
    else:
        s["notice"] = "Please answer the current question or ask to cancel Doctor Connect."
    s["revision"] = current["revision"] + 1
    return s, (s["notice"] + " " + prompt(s)).strip()
