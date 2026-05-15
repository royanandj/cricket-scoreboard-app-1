# CricStyle Cricket Scoring App

A mobile-friendly Streamlit cricket scoring app inspired by CricHeroes-style local tournament scoring.

## Features

- Create tournaments, teams and players
- Start matches with toss, venue and overs
- Live ball-by-ball scoring
- Runs, extras, wickets and undo support
- Auto score summary and innings progression
- Match records
- Automatic points table with W, L, T/NR, points and NRR
- Backup and restore database
- Mobile friendly buttons and layout

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository.
2. Upload these files to the repository root.
3. Go to https://share.streamlit.io
4. Click **Create app**.
5. Select your repo.
6. Main file path: `app.py`
7. Deploy.

## Important note about data

Streamlit Community Cloud storage can reset when the app redeploys or sleeps. Use **Backup** after every tournament day and restore it when needed.
