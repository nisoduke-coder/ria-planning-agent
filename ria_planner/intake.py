"""Load client data from files, so you never have to edit Python to run a client.

  * JSON  -> one client   (clients/dana.json)
  * CSV   -> many clients  (clients/book.csv, one row per client)

Only fields that exist on ClientProfile are read; blanks fall back to the
sensible defaults in models.py. Unknown columns are ignored so you can keep
extra notes in your spreadsheet without breaking anything.
"""

import csv
import json

from .models import ClientProfile, MeetingContext

# Fields that must be whole numbers / plain text (everything else is a float).
_INT_FIELDS = {"current_age", "retirement_age", "life_expectancy", "ltc_years"}
_TEXT_FIELDS = {"name", "risk_tolerance", "notes"}
_ALLOWED = set(ClientProfile.__dataclass_fields__.keys())


def _to_profile(data: dict) -> ClientProfile:
    """Turn a plain dict (from JSON or a CSV row) into a ClientProfile."""
    kwargs = {}
    for key, value in data.items():
        if key not in _ALLOWED:
            continue                       # ignore stray columns
        if value is None or value == "":
            continue                       # blank -> use the default
        try:
            if key in _TEXT_FIELDS:
                kwargs[key] = str(value)
            elif key in _INT_FIELDS:
                kwargs[key] = int(float(value))   # handles "65" and "65.0"
            else:
                kwargs[key] = float(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"Could not read field '{key}' with value {value!r}. "
                f"Numbers should look like 65 or 180000 (no $ or commas)."
            )

    try:
        return ClientProfile(**kwargs)
    except TypeError as exc:
        raise ValueError(
            f"Missing a required field for this client. Every client needs at "
            f"least name, current_age, and retirement_age. ({exc})"
        )


def load_client_json(path: str) -> ClientProfile:
    """Read a single client from a JSON file."""
    with open(path) as f:
        return _to_profile(json.load(f))


def load_clients_csv(path: str) -> list:
    """Read many clients from a CSV file (one row each, header on line 1)."""
    with open(path, newline="") as f:
        return [_to_profile(row) for row in csv.DictReader(f)]


def load_meeting_context_json(path: str) -> MeetingContext:
    """Read an optional 'meeting' block from a client JSON file (else defaults)."""
    with open(path) as f:
        meeting = (json.load(f).get("meeting") or {})
    return MeetingContext(
        purpose=str(meeting.get("purpose", "Portfolio review")),
        last_review=str(meeting.get("last_review", "")),
        open_items=str(meeting.get("open_items", "")),
        notes=str(meeting.get("notes", "")),
    )
