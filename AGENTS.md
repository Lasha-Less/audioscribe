# AudioScribe

## Purpose
AudioScribe downloads audio or video from individual YouTube URLs and playlists. It has a CLI and a Tkinter desktop interface. It is primarily for personal use, sharing with friends and family, and practical development experience.

## Working style
- Prioritize efficient development, simplicity, and low cost.
- Use plain language and explain changes briefly.
- Follow our cycle: Idea, Design, Implementation, Testing, Integration, Review.
- Work in small slices. Complete the agreed step before proceeding.
- Discuss design decisions with the user before implementing unagreed behavior.

## Engineering
- Keep reusable logic in the core; keep interfaces thin.
- Give each function one clear responsibility.
- Preserve public result contracts and predictable error structures.
- Prefer explicit, readable code and descriptive names.
- Use comments to explain intent or non-obvious decisions.
- Keep refactoring incremental and separate from behavior changes.
- Avoid unnecessary dependencies and premature abstraction.
- The download workflow must remain usable without a database.
- Document new or modified modules, classes, functions, and methods with concise docstrings.
- Place module docstrings at the top of the file, before imports; place class, function, and method docstrings as the first statement inside their body.
- Explain the purpose and behavior in plain language. Include inputs, return values, side effects, or exceptions where useful.
- Focus on information that helps a future reader understand the code; avoid merely repeating its name.
- Do not document the entire existing codebase during unrelated work.

## Git workflow
- The stable branch is master.
- Use short-lived feature/<description> branches for changes.
- Inspect git status before editing; preserve existing user changes.
- Run relevant checks before integration.
- Do not commit, push, merge, or delete branches unless the user requests it.

## Local verification
- Use the existing Windows virtual environment: .venv\Scripts\python.exe.
- Existing test command:
  .\.venv\Scripts\python.exe -m unittest discover -s tests -v
- Do not perform network downloads or launch the GUI as tests unless requested.

## Current work
- Current slice: C5_SL08_IMP — Set Up Codex in PyCharm’s Terminal.
- This slice adds development instructions and context and verifies project access and existing tests.
- After setup, resume C5_SL07_IMP — Package AudioScribe for Windows.
- Packaging design has already been agreed. Obtain the full packaging handoff before implementing it; do not infer missing decisions.
- Do not change application behavior during this setup slice.
