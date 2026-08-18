# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Small Fission health function used to prove the serverless runtime works."""

import json


def main():
    """Run this module as a command-line entry point."""
    return json.dumps(
        {
            "status": "ok",
            "service": "housing-fission-health",
            "runtime": "fission-python",
        }
    )
