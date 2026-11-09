# Candidate submission checklist

## Local guideline inspected

On 2026-11-08 the latest downloaded regular file by modification time was
`~/Downloads/YottaFlex AI Candidate Project Submission Guidelines.pdf` (one page).
It specifies a 72-hour submission window verified using artifact timestamps, runnable code
with setup/run/verification instructions, a public GitHub repository with meaningful evolution,
prompt history and transparent AI usage, and clear reasoning, tests, assumptions and limitations.
It also expects the candidate to walk through the solution. The actual start/deadline was not
present in the PDF and has not been inferred from file timestamps.

The file was read and visually inspected; its SHA-256 and source treatment are recorded in
`source-manifest.json`. It supplies submission constraints, not customer/business data.
No public redistribution rights were established, so the original PDF is not copied here.

## Before submitting

- Review the delivered implementation and actual verification reports; complete owner-controlled submission tasks.
- Verify a fresh clone using locked dependencies and a clean database.
- Provide starter and full seed generation commands, actual exports/download location and size,
  schema/dictionary, fixed seed/config/version, manifest and validation summary.
- Attach two-run full-volume checksum/count comparison and honest test output.
- Provide a 5-8 minute demo: normal recovery, withdrawal suppression, multi-device/cap conflict,
  recovered/late purchase, four negative findings, one-order attribution and reconciled metrics.
- Document exact 10,000-campaign/attempt interpretation and show accepted send counts separately.
- Complete `prompt-history.md`: preserve actual prompts/responses or export the session transcript.
  Link transcript artifacts and map AI help to code, personal edits/review and validation.
- Complete `ai-usage.md` with what the candidate personally checked. Never mark AI review as
  the candidate's own work. Explain the deterministic design and trade-offs in your own words.
- Keep genuine commit/artifact timestamps and meaningful incremental commits. Never backdate
  files or commits to fit the submission window. Check the actual deadline with the organizer.
- Prepare a public GitHub repository with README, source, tests, documentation and small fixture
  samples. Exclude `.env`, real contacts, local bridge tokens, caches and large generated data.
  If required, publish full exports as a release/download with checksums. Public publishing
  still needs the user's chosen destination and explicit publishing instruction.
- Review synthetic provenance and the license you intend to grant for your own code; do not
  silently assign licensing to third-party files. No repository license was chosen for you.

## Suggested walkthrough

1. State the workflow and the policy defaults; point to architecture and data model.
2. Start from an empty database and generate/import starter data with one command sequence.
3. Show one cart's activity, abandonment boundary, consent, queue, accepted send and click.
4. Purchase the cart; show its single winning credit and the aggregate metric identities.
5. Withdraw consent between scheduling and dispatch and show the suppressing evidence.
6. Demonstrate labelled bad claims and the detector's findings, then show evaluator metrics.
7. Present full-volume validation/reproducibility evidence and candid limits/AI disclosure.

Suggested commit milestones: storage/policy contracts; deterministic generator; ingestion and
scanner; consent-safe dispatch; attribution/evaluation; console; final evidence/documentation.
Create these commits as the corresponding work happens rather than inventing past history.
