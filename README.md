# AI CV Ranker (Ollama + Qwen3 14B)

Python CLI agent that reads CV files from a folder and ranks candidates from `0` to `100` against user requirements.

- `100`: best match
- `0`: no meaningful match

It uses local Ollama at `http://localhost:11434` with model `qwen3:14b` by default.

## Features

- Reads CV files from one folder (`.txt`, `.md`, `.docx`, `.pdf`)
- LLM-based scoring using Ollama (`qwen3:14b`)
- Heuristic fallback when Ollama is unavailable
- Structured output with score, matched/missing skills, and reasoning
- JSON or human-readable text output

## Quick Start

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e .
```

Optional PDF parser:

```bash
python3 -m pip install "pypdf>=4.0.0"
```

## Run

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
PYTHONPATH=src python3 -m cv_ranker \
  --cv-folder tests/fixtures/cvs \
  --requirements "Minimum 5 years of experience, required skills: Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis" \
  --model qwen3:14b \
  --ollama-url http://localhost:11434 \
  --mode auto \
  --output text
```

If Ollama is not running, use deterministic mode:

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
PYTHONPATH=src python3 -m cv_ranker \
  --cv-folder tests/fixtures/cvs \
  --requirements "Minimum 5 years of experience, required skills: Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis" \
  --mode heuristic
```

JSON output:

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
PYTHONPATH=src python3 -m cv_ranker \
  --cv-folder tests/fixtures/cvs \
  --requirements "Minimum 5 years of experience, required skills: Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis" \
  --output json
```

## Test

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
PYTHONPATH=src python3 -m unittest discover -s tests -p "test_*.py"
```

## Notes

- PDF extraction requires `pypdf`.
- `.docx` extraction works without extra dependencies.
- For production use, you can improve scoring by adding weighted requirements and hard filters.

