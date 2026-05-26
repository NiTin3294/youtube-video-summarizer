website link - https://youtube-video-summarizer-yek6iw76uwmrmhqto83hha.streamlit.app/
# YouTube Video Summarizer

A Python + Streamlit app that summarizes YouTube videos from captions/transcripts.

## Features

- Paste a YouTube URL and watch the video inside the app.
- Fetches YouTube captions/transcripts when available.
- Generates:
  - Quick summary
  - Detailed explanation
  - Key points
  - Timestamped chapters
  - Important moments
  - Study notes
  - Searchable transcript
- Exports the generated notes as Markdown.
- Supports manual transcript paste when a video has no public transcript.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL Streamlit prints in the terminal.

## Notes

This app uses an offline extractive summarizer, so it does not require an API key. It needs an internet connection to fetch YouTube transcripts.
