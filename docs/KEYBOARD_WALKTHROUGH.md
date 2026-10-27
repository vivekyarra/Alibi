# Keyboard-only walkthrough

Date: 2026-10-27
URL tested: https://5u7suz00bi.execute-api.us-east-1.amazonaws.com (live AWS deployment)
Pages tested: `#/` (home), `#/jobs/aws3-dropped-frames-040218` (finished job), plus Enter on a nav link to `#/limitations`.
Browser: Chromium-based browser pane, keys sent with Tab, Shift+Tab and Enter only.
Rules followed: no file was uploaded, no form was submitted, no demo case was run.

## Home page steps

1. Load `#/`. Focus starts on the page heading (H1, "Check if a video is real from the light in the room").
2. Press Tab from the top of the page. Tab order observed:
   1. Skip to main content (hidden until focused, then shown top left)
   2. GRIDPRINT Verify (brand link)
   3. Home
   4. Reviewer
   5. Limitations
   6. Judge guide
   7. Use light theme (button)
   8. Read the limitations (link in the intro text)
   9. Video file (file input)
   10. Claimed grid zone (select)
   11. Claimed recording time (UTC) (datetime input)
   12. Claimed time tolerance (seconds) (number input)
   13. Capture sidecar file (file input)
   14. Upload and check (submit button, focused only)
   15. Live grid frequency: Grid zone (select)
   16. Eight demo-case Run buttons, in page order (focused only, never pressed)
3. Tab after the last Run button wraps back to Skip to main content.
4. Shift+Tab moves back through the same order. Shift+Tab from the skip link wraps to the last Run button.
5. Enter on Skip to main content moves focus to `<main id="main">`.
6. Enter on the Limitations nav link opens `#/limitations`. Focus moves to the H1 "Limitations". The page title changes to "Limitations - GRIDPRINT Verify".

## Job page steps

1. Load `#/jobs/aws3-dropped-frames-040218`. Focus starts on the H1 "Job aws3-dropped-frames-040218".
2. Tab order observed: Refresh status (button), then it wraps to Skip to main content, the brand link, the nav links and Use light theme.
3. The verdict card, reasons, agent trace and downloads are static text. They are not tab stops. They are read in page order after the Progress section.
4. The page has headings for each section: Progress, Verdict, Agent trace, Downloads.
5. The status line has `role="status"`. The agent trace text sits in an `aria-live="polite"` region.

## What worked

- Every interactive control on the home page is reachable with Tab and Shift+Tab.
- There is a working skip link.
- Every focused element showed a visible focus ring: a solid outline, about 2.7 px, light blue (rgb 138, 180, 248), on the dark theme.
- Each demo Run button has a distinct accessible name, for example "Run demo case: Dropped frames with original timestamps (SYNTHETIC)". The visible text is only "Run".
- On route change, focus moves to the new page's H1 and the document title updates.
- Nav links open pages with Enter.

## Problems found

- On both finished AWS jobs (`aws3-capture-verified-040158` and `aws3-dropped-frames-040218`), the Agent trace section says "No agent steps were recorded." and the Downloads section says "No files are available yet." So there were no trace entries or download links to reach by keyboard. This is a content issue on the deployed jobs, not a keyboard issue, but it means the trace and downloads could not be tested.
- Not tested: the native file picker dialog, opening the select lists with arrow keys, and the Reviewer sign-in form (no token entered, no form submitted).
- Focus colours were checked only in the dark theme.
