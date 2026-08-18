# Privacy and publication checklist

## Excluded from Git

- raw social posts/comments and raw official data dumps;
- usernames, handles, email addresses, phone numbers and unredacted URLs;
- team member names and student identifiers;
- screenshots/course reports with identities;
- kubeconfigs, service-account tokens, Model Studio keys and hash salts;
- Elasticsearch snapshots and Redis volumes.

## Controlled preprocessing

`python -m housing_agent.preprocess PRIVATE.jsonl PROTECTED_OUTPUT.jsonl` performs allowlist selection, common identifier redaction and salted ID hashing. It is a minimum technical control, not a complete privacy guarantee. Inspect a sample and the source license before indexing or publishing any output.

For Spartan, `scripts/slurm/preprocess_housing.sbatch` requires protected input/output paths and a job-only `HOUSING_HASH_SALT`. Store artifacts on project GPFS, not a public Git checkout.

## Public audit

Run before every public commit:

```bash
python scripts/public_audit.py .
git status --short
git diff --cached --check
```

Also run a dedicated secret scanner such as Gitleaks in CI before GitHub publication. The included audit is deliberately narrow and cannot prove absence of every identifier.
