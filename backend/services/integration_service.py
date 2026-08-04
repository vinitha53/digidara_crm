from flask import current_app

from extensions import db
from models import Integration


PROVIDERS = {
    "gmail": {"name": "Gmail", "type": "email"},
    "whatsapp": {"name": "WhatsApp", "type": "whatsapp"},
}


def configured_agency_id():
    value = current_app.config.get("CRM_AGENCY_ID")
    return int(value) if value not in (None, "") else None


def integration_record(provider, active_only=True):
    definition = PROVIDERS.get(provider)
    if not definition:
        return None
    query = Integration.query.filter_by(type=definition["type"])
    if active_only:
        query = query.filter_by(is_active=True)
    agency_id = configured_agency_id()
    if agency_id is not None:
        exact = query.filter_by(agency_id=agency_id).order_by(Integration.id.desc()).first()
        if exact:
            return exact
    shared = query.filter_by(agency_id=None).order_by(Integration.id.desc()).first()
    return shared


def integration_config(provider):
    record = integration_record(provider)
    return dict(record.config or {}) if record else {}


def save_integration_config(provider, updates):
    definition = PROVIDERS[provider]
    agency_id = configured_agency_id()
    record = Integration.query.filter_by(type=definition["type"], agency_id=agency_id).first()
    if not record:
        record = Integration(
            name=definition["name"],
            type=definition["type"],
            agency_id=agency_id,
            is_active=True,
            config={},
        )
        db.session.add(record)
    config = dict(record.config or {})
    config.update({key: value for key, value in updates.items() if value not in (None, "")})
    record.name = definition["name"]
    record.is_active = True
    record.config = config
    return record
