# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Flask application factory for the housing analytics REST API."""

from __future__ import annotations

import os

from flask import Flask, jsonify
from flask_cors import CORS

from backend.api.housing_routes import housing_bp
from backend.api.official_routes import official_bp
from backend.api.analysis_routes import analysis_bp
from backend.api.cache_routes import cache_bp


ROUTE_SUMMARY = {
    "housing": [
        "/api/health",
        "/api/housing/volume-by-platform",
        "/api/housing/timeseries",
        "/api/housing/top-query-keywords",
        "/api/housing/by-city-context",
        "/api/housing/search?q=rent&size=5",
    ],
    "official": [
        "/api/official/health",
        "/api/official/overview",
        "/api/official/source-groups",
        "/api/official/by-state",
        "/api/official/by-period",
        "/api/official/search?q=Aberfoyle%20Park%20median%20rent&size=5",
    ],
    "analysis": [
        "/api/analysis/health",
        "/api/analysis/dashboard/overview",
        "/api/analysis/housing/sentiment-summary",
        "/api/analysis/housing/by-city-context",
        "/api/analysis/housing/top-query-keywords",
        "/api/analysis/official/period-by-source-group",
    ],
}


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # The notebook frontend may run from a different local port during demo.
    CORS(app)

    app.register_blueprint(housing_bp)
    app.register_blueprint(official_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(cache_bp)

    @app.get("/")
    def root():
        """Return a small service description for the root endpoint."""
        return jsonify(
            {
                "service": "COMP90024 housing backend API",
                "routes": ROUTE_SUMMARY,
            }
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "9090")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
