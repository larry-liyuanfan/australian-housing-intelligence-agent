# Team project attribution and publication boundary

## Team-authored baseline

`team12_platform/` is a sanitized snapshot of **COMP90024 Team 12**, University of Melbourne, Semester 1 2026. The original course repository is referenced in the team report as:

`https://gitlab.unimelb.edu.au/comp90024_team_12/comp90024_team_12`

All code, deployment manifests, analytics, frontend assets, documentation and aggregate figures inside `team12_platform/` must be described as Team 12 work unless independent commit evidence establishes a narrower contribution. Member identities and student identifiers are intentionally omitted from this public copy.

## Personal portfolio extension

The following top-level assets form the new personal Agentic Search extension and are separate from the course baseline:

- `src/housing_agent/` and `tests/`;
- `eval/` and generated synthetic evaluation artifacts;
- `compose.yaml`, root `Dockerfile`, `deploy/` and Spartan preprocessing script;
- root architecture, decision, evidence, privacy and interview documentation.

This boundary prevents team-level data scale, Kubernetes/Fission deployment, APIs or analytics from being presented as independently authored personal outcomes.

## Public-copy transformations

- Removed the original processed data directory and identifiable normalized samples.
- Retained only a clearly synthetic schema sample for the historical smoke test.
- Cleared every notebook output/execution count and removed member metadata.
- Removed command screenshots and the report PDF.
- Replaced member names/student IDs with Team 12 attribution or anonymous role labels.
- Removed embedded password defaults and branch/user identifiers; credentials must come from runtime secrets.

The sanitizer is reproducible via `scripts/sanitize_team12_import.py`. `scripts/public_audit.py` provides an additional high-risk pattern scan, but manual review and a dedicated secret scanner remain required before publication.

## License

No open-source license is granted for the Team 12 snapshot. Do not add a license or accept external contributions until every team member/course-policy requirement has been confirmed.
