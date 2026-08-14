"""Development entry point for VerifyLite."""

import os

from app import create_app
from app.config import DEFAULT_PORT

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    app.run(host="0.0.0.0", port=port, debug=False)
