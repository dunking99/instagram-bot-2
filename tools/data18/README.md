# data18 scraper

Standalone. Not connected to any other project.

    cd ~/data18-scraper
    .venv/bin/python setup_session.py     # once: click "I AGREE" in the window that opens
    .venv/bin/python server.py            # dashboard at http://127.0.0.1:8790
    .venv/bin/python scraper.py "Kyler Quinn"   # or use it from the command line (JSON)

- Results are cached in `data/results/<slug>.json`; "Re-scrape" refreshes one.
- If the dashboard says the session expired, rerun `setup_session.py`.
- Pages come from data18's `/sys/page.php` listing endpoint (30 videos per page, stops at the first empty page).
