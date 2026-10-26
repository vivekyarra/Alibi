# Face-composite clips (human task H7)

This procedure makes the face-composite test clips in `SPEC.md` Part 11.3. These clips test the EXPERIMENTAL face-region check (stage S12) and demo case 8.

## Rules

1. Use only consenting team members. Each person signs `eval/templates/consent_form.md` and ticks the "Face composites" box before any recording.
2. Never use the face of a person who did not consent. Do not use faces from the internet, from public datasets of real people, or of public figures.
3. Use an open-source face-swap tool. Before first use, record in `docs/LICENSES.md`: tool name, version or commit, repository URL, license, and the date. Also record the tool in `docs/DECISIONS.md` with the reason for the choice.
4. Do not use a tool whose license forbids this research use.
5. Run the tool on a team computer. Do not upload team faces to an online face-swap service.
6. Label every output as synthetic (`class = synthetic` in the manifest).
7. Keep the source clips, the composites, and the consent forms outside the repository.

## Procedure

1. Choose the tool (rule 3) and install it per its own instructions in a separate environment. Do not add it to the GRIDPRINT dependencies.
2. Record **target clips** with GRIDPRINT Capture under mains-powered light. One consenting team member (person A) faces the camera. Use the dataset procedure in `eval/DATASET.md` section 3 (session ID, filmed NTP clock, manifest entry). These targets are normal authentic clips.
3. Record **source material** of a second consenting team member (person B): a short clip or photos of the face. Use any lighting.
4. Make the composite: replace the face of person A in the target clip with the face of person B.
5. Export the composite as MP4. Do not change the frame rate or the frame timestamps on purpose. Write down the export settings.
6. Name the file `<target_clip_id>__faceswap.mp4` and put it in the target clip's session folder.
7. Add a manifest entry:
   - `clip_id`: `<target_clip_id>__faceswap`
   - `class`: `synthetic`
   - `people_present`: `true`; `consent_ids`: the IDs of person A and person B
   - all other recording fields copied from the target clip
   - `compression`: `original` if the tool output was not recompressed after export; otherwise the matching value
8. Write in the session log: tool name and version, model or weights used and their license, export settings, date.
9. Make enough composites for the experimental results table. Use at least two different phone models and two lighting types.

## How the results are reported

- Face-region results are reported in a separate table, labeled `EXPERIMENTAL`.
- A face-region result is never the only basis for `CONTRADICTED` (rule R9).
- If the face-region check finds no difference, that is reported as is. It does not mean the composite is authentic.

## Validation

`make validate-dataset` checks that each `__faceswap` entry has `class = synthetic`, `people_present = true`, and at least one consent ID.
