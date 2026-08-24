from __future__ import annotations
import os

# Neutralise the deployment secrets before any test module imports an app.
#
# The services read these at IMPORT time — logic/chat/app.py and
# logic/bills/app.py call install_password_gate() while building the module-level
# `app`, and load_dotenv() has already pulled the repo's real .env into the
# environment by then. A monkeypatch fixture runs far too late to help: the
# middleware is attached to the app object before the first test starts, and the
# gated endpoints answer 401 for the rest of the session.
#
# Empty string rather than del: load_dotenv(override=False) skips keys already
# present in os.environ, so an empty value stays empty, whereas a deleted key
# gets refilled from .env on the very next import.
for _var in ("APP_PASSWORD", "BILLS_APP_PASSWORD", "BILLS_ADMIN_TOKEN",
             "CHAT_FEEDBACK_TOKEN"):
    os.environ[_var] = ""
