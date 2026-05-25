from __future__ import annotations

import html
import math
import re
import textwrap
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi


STOP_WORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "now",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "s",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "t",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


@dataclass(frozen=True)
class TranscriptLine:
    start: float
    duration: float
    text: str


@dataclass(frozen=True)
class Sentence:
    text: str
    start: float
    score: float = 0.0


def extract_video_id(value: str) -> str | None:
    value = value.strip()
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([A-Za-z0-9_-]{11})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        r"^[A-Za-z0-9_-]{11}$",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return None


def format_timestamp(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize_words(text: str) -> list[str]:
    return [
        word
        for word in re.findall(r"[a-zA-Z][a-zA-Z']{2,}", text.lower())
        if word not in STOP_WORDS
    ]


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    pieces = re.split(r"(?<=[.!?])\s+", text)
    return [piece.strip(" -") for piece in pieces if len(piece.strip()) > 20]


def fetch_transcript(video_id: str, languages: list[str]) -> list[TranscriptLine]:
    if hasattr(YouTubeTranscriptApi, "get_transcript"):
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
    else:
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=languages)

    lines = []
    for item in transcript:
        if isinstance(item, dict):
            raw_text = item.get("text", "")
            start = item.get("start", 0)
            duration = item.get("duration", 0)
        else:
            raw_text = getattr(item, "text", "")
            start = getattr(item, "start", 0)
            duration = getattr(item, "duration", 0)

        text = clean_text(raw_text)
        if text:
            lines.append(TranscriptLine(start=float(start), duration=float(duration), text=text))
    return lines


def transcript_error_message(exc: Exception) -> str:
    raw = str(exc)
    if "blocking requests from your IP" in raw or "cloud provider" in raw:
        return (
            "YouTube blocked transcript requests from this hosted app. "
            "Paste or upload the transcript below and summarize again."
        )
    if "disabled" in raw.lower():
        return "This video has transcripts disabled. Paste or upload a transcript to summarize it."
    if "no transcript" in raw.lower():
        return "No public transcript was found for this video. Paste or upload a transcript to summarize it."
    return "I could not fetch captions for this video. Paste or upload a transcript to summarize it."


def parse_timestamp(value: str) -> float | None:
    match = re.search(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[,.](\d{1,3}))?", value)
    if not match:
        return None

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    milliseconds = int((match.group(4) or "0").ljust(3, "0"))
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def timestamped_transcript_to_lines(text: str) -> list[TranscriptLine]:
    lines: list[TranscriptLine] = []
    pending_start: float | None = None
    pending_text: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.isdigit() or line.upper() == "WEBVTT":
            continue

        if "-->" in line:
            if pending_start is not None and pending_text:
                lines.append(TranscriptLine(pending_start, 8.0, clean_text(" ".join(pending_text))))
            pending_start = parse_timestamp(line.split("-->", 1)[0])
            pending_text = []
            continue

        inline_timestamp = re.match(r"^\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s+(.+)$", line)
        if inline_timestamp:
            if pending_start is not None and pending_text:
                lines.append(TranscriptLine(pending_start, 8.0, clean_text(" ".join(pending_text))))
            pending_start = parse_timestamp(inline_timestamp.group(1))
            pending_text = [inline_timestamp.group(2)]
            continue

        if pending_start is not None:
            pending_text.append(line)

    if pending_start is not None and pending_text:
        lines.append(TranscriptLine(pending_start, 8.0, clean_text(" ".join(pending_text))))

    return [line for line in lines if line.text]


def manual_transcript_to_lines(text: str) -> list[TranscriptLine]:
    timestamped_lines = timestamped_transcript_to_lines(text)
    if timestamped_lines:
        return timestamped_lines

    paragraphs = [clean_text(part) for part in re.split(r"\n+", text) if clean_text(part)]
    if not paragraphs:
        return []

    lines: list[TranscriptLine] = []
    cursor = 0.0
    for paragraph in paragraphs:
        duration = max(8.0, min(35.0, len(paragraph.split()) / 2.6))
        lines.append(TranscriptLine(start=cursor, duration=duration, text=paragraph))
        cursor += duration
    return lines


def lines_to_text(lines: Iterable[TranscriptLine]) -> str:
    return " ".join(line.text for line in lines)


def make_sentences(lines: list[TranscriptLine]) -> list[Sentence]:
    sentences: list[Sentence] = []
    for line in lines:
        chunks = split_sentences(line.text)
        if chunks:
            sentences.extend(Sentence(text=chunk, start=line.start) for chunk in chunks)
        elif len(line.text.split()) > 5:
            sentences.append(Sentence(text=line.text, start=line.start))
    return sentences


def score_sentences(sentences: list[Sentence]) -> list[Sentence]:
    words = tokenize_words(" ".join(sentence.text for sentence in sentences))
    frequencies = Counter(words)
    if not frequencies:
        return sentences

    max_frequency = max(frequencies.values())
    normalized = {word: count / max_frequency for word, count in frequencies.items()}
    scored: list[Sentence] = []

    for sentence in sentences:
        sentence_words = tokenize_words(sentence.text)
        if not sentence_words:
            score = 0.0
        else:
            raw_score = sum(normalized.get(word, 0.0) for word in sentence_words)
            length_penalty = 1 + abs(len(sentence_words) - 18) / 28
            score = raw_score / length_penalty
        scored.append(Sentence(text=sentence.text, start=sentence.start, score=score))

    return scored


def top_sentences(sentences: list[Sentence], count: int) -> list[Sentence]:
    ranked = sorted(sentences, key=lambda sentence: sentence.score, reverse=True)[:count]
    return sorted(ranked, key=lambda sentence: sentence.start)


def make_summary(sentences: list[Sentence], detail: str) -> list[Sentence]:
    if detail == "Short":
        count = 5
    elif detail == "Deep":
        count = 14
    else:
        count = 9
    count = min(count, max(3, math.ceil(len(sentences) * 0.18)))
    return top_sentences(sentences, count)


def chunk_lines(lines: list[TranscriptLine], seconds_per_chapter: int) -> list[list[TranscriptLine]]:
    if not lines:
        return []

    chunks: list[list[TranscriptLine]] = []
    current: list[TranscriptLine] = []
    start = lines[0].start

    for line in lines:
        if current and line.start - start >= seconds_per_chapter:
            chunks.append(current)
            current = []
            start = line.start
        current.append(line)

    if current:
        chunks.append(current)
    return chunks


def title_from_text(text: str) -> str:
    words = tokenize_words(text)
    common = [word for word, _ in Counter(words).most_common(5)]
    if not common:
        return "Main idea"
    return " ".join(word.capitalize() for word in common[:4])


def make_chapters(lines: list[TranscriptLine], seconds_per_chapter: int) -> list[dict[str, str]]:
    chapters = []
    for chunk in chunk_lines(lines, seconds_per_chapter):
        chunk_text = lines_to_text(chunk)
        chapter_sentences = score_sentences(make_sentences(chunk))
        best_sentence = top_sentences(chapter_sentences, 1)
        chapters.append(
            {
                "time": format_timestamp(chunk[0].start),
                "title": title_from_text(chunk_text),
                "note": best_sentence[0].text if best_sentence else textwrap.shorten(chunk_text, 170),
            }
        )
    return chapters


def make_key_points(sentences: list[Sentence], count: int) -> list[Sentence]:
    return top_sentences(sentences, count)


def make_terms(full_text: str, count: int = 12) -> list[tuple[str, int]]:
    words = tokenize_words(full_text)
    ignored = {"video", "like", "really", "going", "think", "know", "want", "make", "get"}
    return [(word, qty) for word, qty in Counter(words).most_common(count * 2) if word not in ignored][:count]


def make_markdown(
    video_url: str,
    summary: list[Sentence],
    key_points: list[Sentence],
    chapters: list[dict[str, str]],
    terms: list[tuple[str, int]],
) -> str:
    lines = [
        "# YouTube Video Summary",
        "",
        f"Video: {video_url}",
        "",
        "## Quick Summary",
        "",
    ]
    lines.extend(f"- [{format_timestamp(item.start)}] {item.text}" for item in summary)
    lines.extend(["", "## Key Points", ""])
    lines.extend(f"- [{format_timestamp(item.start)}] {item.text}" for item in key_points)
    lines.extend(["", "## Timestamped Chapters", ""])
    lines.extend(f"- **{chapter['time']} - {chapter['title']}**: {chapter['note']}" for chapter in chapters)
    lines.extend(["", "## Important Terms", ""])
    lines.extend(f"- {word} ({count})" for word, count in terms)
    return "\n".join(lines)


def render_video(video_id: str) -> None:
    video_src = f"https://www.youtube.com/embed/{video_id}"
    if hasattr(st, "iframe"):
        st.iframe(video_src, height=390)
    else:
        st.components.v1.iframe(src=video_src, height=390, scrolling=False)


def render_timestamped_items(items: list[Sentence]) -> None:
    for item in items:
        st.markdown(f"**{format_timestamp(item.start)}**  {item.text}")


def render_transcript(lines: list[TranscriptLine], query: str) -> None:
    normalized_query = query.lower().strip()
    shown = 0
    for line in lines:
        if normalized_query and normalized_query not in line.text.lower():
            continue
        st.markdown(f"`{format_timestamp(line.start)}` {line.text}")
        shown += 1
        if shown >= 120:
            st.caption("Showing first 120 matching transcript lines.")
            break


def app() -> None:
    st.set_page_config(
        page_title="YouTube Video Summarizer",
        page_icon="YT",
        layout="wide",
    )

    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.4rem; }
        iframe { border-radius: 8px; }
        [data-testid="stMetricValue"] { font-size: 1.45rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("YouTube Video Summarizer")
    st.caption("Paste a YouTube link, view the video, and turn captions into clear notes with timestamps.")

    with st.sidebar:
        st.header("Input")
        video_url = st.text_input("YouTube URL or video ID", placeholder="https://www.youtube.com/watch?v=...")
        languages_text = st.text_input("Transcript languages", value="en,en-US,en-GB,hi")
        detail = st.segmented_control("Summary depth", ["Short", "Balanced", "Deep"], default="Balanced")
        key_point_count = st.slider("Key points", min_value=5, max_value=20, value=10)
        chapter_minutes = st.slider("Chapter length", min_value=1, max_value=10, value=3)
        st.divider()
        uploaded_transcript = st.file_uploader("Upload transcript", type=["txt", "srt", "vtt"])
        manual_text = st.text_area(
            "Paste transcript",
            height=180,
            placeholder="Paste transcript here if YouTube captions are unavailable.",
        )
        summarize_clicked = st.button("Summarize", type="primary", use_container_width=True)

    if not summarize_clicked:
        st.info("Enter a YouTube URL and click Summarize.")
        return

    uploaded_text = ""
    if uploaded_transcript is not None:
        uploaded_text = uploaded_transcript.getvalue().decode("utf-8", errors="ignore")
    fallback_text = manual_text.strip() or uploaded_text.strip()

    video_id = extract_video_id(video_url)
    if not video_id and not fallback_text:
        st.error("Please enter a valid YouTube URL, video ID, or paste a manual transcript.")
        return

    languages = [language.strip() for language in languages_text.split(",") if language.strip()]
    transcript_lines: list[TranscriptLine] = []
    transcript_source = "YouTube captions"

    if video_id:
        try:
            transcript_lines = fetch_transcript(video_id, languages)
        except Exception as exc:
            if fallback_text:
                transcript_lines = manual_transcript_to_lines(fallback_text)
                transcript_source = "manual transcript"
                st.warning("Could not fetch YouTube captions, so I used the transcript you provided.")
            else:
                st.error(transcript_error_message(exc))
                return
    elif fallback_text:
        transcript_lines = manual_transcript_to_lines(fallback_text)
        transcript_source = "manual transcript"

    full_text = lines_to_text(transcript_lines)
    sentences = score_sentences(make_sentences(transcript_lines))

    if len(full_text.split()) < 40 or not sentences:
        st.error("The transcript is too short to summarize well. Try a longer video or paste more transcript text.")
        return

    summary = make_summary(sentences, detail)
    key_points = make_key_points(sentences, key_point_count)
    chapters = make_chapters(transcript_lines, chapter_minutes * 60)
    terms = make_terms(full_text)

    left, right = st.columns([1.1, 0.9], vertical_alignment="top")
    with left:
        if video_id:
            render_video(video_id)
        else:
            st.info("Manual transcript mode does not include a video preview.")

    with right:
        total_seconds = max(line.start + line.duration for line in transcript_lines)
        word_count = len(full_text.split())
        st.subheader("At a Glance")
        metric_cols = st.columns(3)
        metric_cols[0].metric("Length", format_timestamp(total_seconds))
        metric_cols[1].metric("Words", f"{word_count:,}")
        metric_cols[2].metric("Source", transcript_source)
        st.markdown("**Core idea**")
        st.write(summary[0].text)

        markdown = make_markdown(video_url or "Manual transcript", summary, key_points, chapters, terms)
        st.download_button(
            "Download notes",
            data=markdown,
            file_name="youtube-summary.md",
            mime="text/markdown",
            use_container_width=True,
        )

    tabs = st.tabs(["Summary", "Key Points", "Timestamps", "Study Notes", "Transcript"])

    with tabs[0]:
        st.subheader("Clear Explanation")
        for index, item in enumerate(summary, start=1):
            st.markdown(f"**{index}. [{format_timestamp(item.start)}]** {item.text}")

    with tabs[1]:
        st.subheader("Key Points")
        render_timestamped_items(key_points)

    with tabs[2]:
        st.subheader("Timestamped Chapters")
        for chapter in chapters:
            st.markdown(f"**{chapter['time']} - {chapter['title']}**")
            st.write(chapter["note"])

    with tabs[3]:
        st.subheader("Study Notes")
        st.markdown("**Important terms**")
        st.write(", ".join(f"{word} ({count})" for word, count in terms))
        st.markdown("**Memory prompts**")
        for item in key_points[:6]:
            st.markdown(f"- What does the speaker mean around **{format_timestamp(item.start)}** when discussing: {item.text}")

    with tabs[4]:
        st.subheader("Search Transcript")
        query = st.text_input("Search words in transcript")
        render_transcript(transcript_lines, query)


if __name__ == "__main__":
    app()
