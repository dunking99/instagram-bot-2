# Postroom / Light table: notes for Claude Code

**Read `HANDOFF.md` first.** It has the current state, what was verified and what was not, the open work in priority order, and how the owner likes to work.

Short version of the rules:
- You are on the owner's Mac with a network: run things live and verify, do not guess from saved pages.
- Brief, plain explanations. Report what was verified versus inferred. Never claim a file was saved or pushed without checking.
- Dashboards with buttons, not scripts or folders. Do not edit the original Postroom (`server.py`, `ui/`) unless asked.
- Position model is B/32 only. Delete nothing without a yes. Keep requests to the sites polite; never try to defeat Cloudflare or logins.
- Commands you give the owner must paste cleanly into zsh: no `#` comments inside pasted blocks.
- Repo layout: `tools/{data18,links,video-finder,stream-test}`; the cloud work is on branch `claude/jolly-cannon-88sel9`.
