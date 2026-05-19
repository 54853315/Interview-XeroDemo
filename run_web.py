#!/usr/bin/env python3
"""Run the Flask web application."""

import os
from dotenv import load_dotenv
from src.xerodemo.web.app import create_app

load_dotenv()

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", 5000))
    app.run(host="localhost", port=port, debug=True)
