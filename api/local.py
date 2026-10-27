"""`make local`: API + worker (fallback planner by default) + built web app, all with local adapters (SPEC 10.7).

The local reviewer token is read from GRIDPRINT_REVIEWER_TOKEN or generated once into work/local_reviewer_token.txt.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import uvicorn

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    tok_file = REPO / "work" / "local_reviewer_token.txt"
    if not os.environ.get("GRIDPRINT_REVIEWER_TOKEN"):
        tok_file.parent.mkdir(parents=True, exist_ok=True)
        if not tok_file.exists():
            tok_file.write_text(secrets.token_urlsafe(24))
        os.environ["GRIDPRINT_REVIEWER_TOKEN"] = tok_file.read_text().strip()
    from api.app import create_app

    app = create_app()  # also serves web/dist when it has been built
    print(f"GRIDPRINT local: http://127.0.0.1:8000  (reviewer token in {tok_file})")
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
