# Responsible use

This document implements `SPEC.md` Part 13.

## 1. What GRIDPRINT is and is not

GRIDPRINT reads the grid frequency from the flicker of mains-powered lights in a video. It compares that signal with a reference log of the real grid.

GRIDPRINT is not:
- a deepfake classifier. It does not judge whether pixels look AI-made;
- a face recognition or identity system;
- a location tracker. The only location output is the grid zone;
- not cryptographic proof of authenticity.

A missing signal is never evidence that a video is fake. Many authentic videos have no usable signal (daylight, battery lamps, phone anti-banding).

GRIDPRINT gives exactly three verdicts: `VERIFIED`, `CONTRADICTED`, `INCONCLUSIVE`.

## 2. Risks and controls

| Risk | Control |
|---|---|
| Revealing when an anonymous source recorded a video could endanger them. | An uploader notice is shown before analysis. Output is limited to time and grid zone. Uploads and results have short retention. Reports are not shared publicly by default. Newsrooms get guidance on secure handling (section 5). |
| A false `CONTRADICTED` harms a truthful person. | Every `CONTRADICTED` result needs human review before the report is final. Thresholds are calibrated to a false-`CONTRADICTED` target that is written down before test data is seen. Every report has a limitations box. Reviewer notes are stored. |
| Over-trust in a `VERIFIED` result. | The report states what was checked and what was not checked. The time uncertainty is shown. Experimental items are labeled `EXPERIMENTAL`. |
| Face data misuse. | Face detection is used only for the experimental band check. No recognition. No embeddings. No face crops are kept beyond the job retention. |
| Electrical injury (Node). | Rule R11: the Node never connects electronics directly to mains. Use only a certified plug-in AC-to-AC adapter. See `node/hardware/SAFETY.md`. |
| Dataset privacy. | Consent for every filmed person. Restricted dataset access. No faces of people who did not consent. Consent forms are stored outside the repository. |
| Licenses. | Licenses of models, tools, and datasets are recorded in `docs/LICENSES.md`. |

## 3. Security controls

- TLS for all network traffic.
- Encryption at rest with SSE-KMS for S3 buckets.
- Presigned upload URLs with short expiry (`limits.presign_expiry_s` in `config/default.yaml`).
- Strict input validation: container allow list, file size limit, duration limit, decode timeouts.
- FFmpeg runs in a non-root container.
- Dependency and container scanning in CI.
- Least-privilege IAM role per service. The worker may invoke only the pinned Bedrock model.
- Amazon Cognito login for reviewers (`reviewer` group).
- Structured audit log of reviewer decisions (reviewer, time, decision, note).
- Anonymous uploads are rate-limited by AWS WAF.
- Secrets are kept in AWS Secrets Manager, never in the repository.
- Uploads and results are deleted by S3 lifecycle rules after the configured retention (`limits.upload_retention_hours`, `limits.results_retention_days`).

## 4. Uploader notice (shown before analysis)

Use this text in the Verify web app before the upload starts:

> **Before you upload**
>
> GRIDPRINT checks the light flicker in your video against a log of the power grid.
>
> The result can show **when** the video was recorded and **which power-grid zone** it matches (for example, a whole country or region). It never shows a city, an address, or a finer location.
>
> If the person who recorded this video could be at risk when the recording time is known, do not upload it. Ask a trained verification desk for help first.
>
> We keep your upload for a short time only, then delete it. We do not share the report publicly. Faces are not identified.
>
> A result of `INCONCLUSIVE` does not mean that the video is fake. Many real videos have no usable flicker signal.
>
> [Continue] [Cancel]

## 5. Guidance for newsrooms and verification desks

1. Treat the recording time as sensitive. It can identify a source when combined with other facts.
2. Do not publish the GRIDPRINT report by default. Publish only the conclusion that you need for your story.
3. Store downloaded reports in an access-controlled system. Delete them when the story no longer needs them.
4. Use GRIDPRINT as one input. Combine it with source interviews, open-source checks, and metadata review.
5. A `VERIFIED` result means: a grid signal is present, it matches the reference log uniquely at the reported time, and no significant edit evidence was found. It does not check who recorded the video, what the scene shows, or the audio track.
6. A `CONTRADICTED` result is final only after a human reviewer approves it. Read the reviewer note and the reasons. Contact the source before you make a public claim.
7. An `INCONCLUSIVE` result says nothing about authenticity. It means the check could not be completed.
8. Results marked `EXPERIMENTAL` (face-region check) are not evidence on their own.
9. Ask sources to record with GRIDPRINT Capture when they can. Capture keeps the flicker bands strong and records sensor timing.

## 6. Human control

- The agent cannot write or change a verdict. The verdict comes from deterministic code (`engine/gridprint_engine/verdict.py`).
- The agent cannot edit thresholds or reason codes.
- Only a human reviewer can move a `CONTRADICTED` report from `PENDING_REVIEW` to `FINAL`. A rejection makes the report `FINAL` with verdict `INCONCLUSIVE` and reason `REVIEWER_REJECTED`.
- Every agent step is traced and visible to the user.
