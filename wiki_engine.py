import json
import os
import re

from dotenv import load_dotenv

load_dotenv()

LLM_BACKEND = os.getenv("LLM_BACKEND", "grounded")
NANOGPT_CHECKPOINT = os.getenv("NANOGPT_CHECKPOINT", "models/wiki_nanogpt.pt")


def build_prompt(message, notes):
    context = "\n\n".join(
        f'Title: {note["title"]}\nContent: {note["content"]}'
        for note in notes
    ) or "No notes are available yet."
    return (
        "You are Recall, a concise personal second-brain assistant. "
        "Use only the supplied notes for personal facts. If the notes do not answer the question, "
        "say that clearly and do not invent details.\n\n"
        f"Retrieved memory:\n{context}\n\nUser question: {message}"
    )


def generate_answer(message, notes):
    if LLM_BACKEND == "nanogpt":
        from karpathy_nanogpt import generate

        if not os.path.exists(NANOGPT_CHECKPOINT):
            return "The nanoGPT checkpoint is not trained yet. Run `python train_nanogpt.py` first."
        return generate(build_prompt(message, notes), NANOGPT_CHECKPOINT)
    return grounded_answer(message, notes)


def grounded_answer(message, notes):
    if not notes:
        return "I could not find anything about that in your wiki yet."
    stop_words = {"what", "when", "where", "which", "who", "how", "tell", "about", "my", "me", "the", "are", "is", "do", "have", "i"}
    question_words = {
        word for word in re.findall(r"[a-zA-Z0-9]+", message.lower())
        if word not in stop_words and len(word) > 2
    }
    aliases = {
        "project": {"project", "projects", "worked"},
        "skill": {"skill", "skills", "technology", "technologies", "know"},
        "experience": {"experience", "career", "job", "work"},
        "education": {"education", "study", "degree", "college"},
        "achievement": {"achievement", "achievements", "award", "awards"},
        "leadership": {"leadership", "leader", "team"},
    }
    requested_sections = {section for section, words in aliases.items() if question_words & words}
    snippets = []
    for note in notes[:3]:
        raw_content = note.get("content", "")
        lines = raw_content.splitlines()
        selected = []
        active_section = None
        for line in lines:
            heading = re.match(r"(#{1,6})\s*(.+)", line)
            if heading:
                if len(heading.group(1)) <= 2:
                    active_section = heading.group(2).lower()
            plain_section = re.match(r"^([A-Za-z ]+):\s*$", line)
            if plain_section and plain_section.group(1).lower() in aliases:
                active_section = plain_section.group(1).lower()
            section_matches = active_section and any(section in active_section for section in requested_sections)
            line_matches = question_words & set(re.findall(r"[a-zA-Z0-9]+", line.lower()))
            if not requested_sections or section_matches or (not active_section and line_matches):
                selected.append(line)
        content = re.sub(r"#{1,6}\s*|[*_>`]", "", " ".join(selected))
        content = re.sub(r"\s+", " ", content).strip()
        snippets.append(f'{note.get("title", "Untitled note")}: {content[:520]}')
    return "Here is what I found in your wiki:\n\n" + "\n\n".join(snippets)


def is_usable_answer(answer):
    lowered = answer.lower()
    blocked_phrases = ("interview answer", "always answer as", "user question", "second brain assistant")
    has_repeated_character = bool(re.search(r"(.)\1{7,}", answer))
    return len(answer.strip()) >= 20 and not has_repeated_character and not any(phrase in lowered for phrase in blocked_phrases)


def metadata_answer(message, notes):
    if not re.search(r"\b(author|written by|who wrote|writer)\b", message.lower()):
        return None
    for note in notes:
        match = re.search(r"^[ \t]*Author:[ \t]*([^\r\n]+)", note.get("content", ""), re.IGNORECASE | re.MULTILINE)
        if match:
            return f"The author of \"{note.get('title', 'this title')}\" is {match.group(1).strip()}."
    return None


def answer_question_from_notes(message, notes):
    metadata = metadata_answer(message, notes)
    if metadata:
        return metadata
    try:
        answer = generate_answer(message, notes)
        if not is_usable_answer(answer):
            answer = grounded_answer(message, notes)
    except (TimeoutError, KeyError, RuntimeError, json.JSONDecodeError):
        answer = grounded_answer(message, notes)
    return answer
