from __future__ import annotations

from dataclasses import dataclass, field

from cv_ranker.llm_client import LLMClient

SYSTEM_PROMPT = (
    "You extract structured data from resumes/CVs. Use the "
    "record_cv_structure tool to return the result. Be faithful to the "
    "source text — do not invent employers, dates, or achievements that "
    "aren't in the CV. If a section is missing, return an empty list "
    "(or empty string for summary)."
)

CV_SCHEMA_TOOL = {
    "type": "function",
    "function": {
        "name": "record_cv_structure",
        "description": ("Record the structured summary, technologies, and experience extracted from a candidate's CV."),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Concise professional summary of the candidate's profile and seniority.",
                },
                "technologies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Technologies, languages, frameworks, and tools the candidate has used.",
                },
                "experience": {
                    "type": "string",
                    "description": "Total years of professional experience, e.g. '13 years'.",
                },
            },
            "required": ["summary", "technologies", "experience"],
        },
    },
}


@dataclass
class CVStructure:
    summary: str = ""
    technologies: list[str] = field(default_factory=list)
    experience: str = ""


def extract_cv_structure(llm_client: LLMClient, cv_text: str) -> CVStructure:
    """Use `llm_client` to extract a {summary, technologies, experience} view of `cv_text`."""
    arguments = llm_client.generate_tool_call(
        prompt=f"CV text:\n{cv_text}",
        system=SYSTEM_PROMPT,
        tool=CV_SCHEMA_TOOL,
    )

    summary = str(arguments.get("summary", "")).strip()
    technologies = [str(item).strip() for item in arguments.get("technologies", []) if str(item).strip()]
    experience = str(arguments.get("experience", "")).strip()

    return CVStructure(summary=summary, technologies=technologies, experience=experience)
