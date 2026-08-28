# AI CV Ranker (Ollama locally, vLLM in production)

Python CLI agent that reads CV files from a folder and ranks candidates from `0` to `100` against user requirements.

- `100`: best match
- `0`: no meaningful match

It uses an **OpenAI-compatible chat client** (the official `openai` SDK) so the exact same code path works against:

- **Local:** [Ollama](https://ollama.com) at `http://localhost:11434/v1` (default, model `qwen3:14b`)
- **Prod:** [vLLM](https://docs.vllm.ai)'s OpenAI-compatible server (any URL/model you configure)

## Features

- Reads CV files from one folder (`.txt`, `.md`, `.docx`, `.pdf`)
- LLM-based scoring via any OpenAI-compatible endpoint (Ollama or vLLM)
- Heuristic fallback when the LLM server is unavailable
- Structured output with score, matched/missing skills, and reasoning
- JSON or human-readable text output
- Environment-based config (`local`/`prod`) resolved from env vars, with `local` as the safe default

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

## Configuration (local vs prod)

Settings are resolved by `cv_ranker.config.load_llm_settings()`, backed by
[`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

Which **environment profile** (`local` or `prod`) is picked, in order:

1. `--env` CLI flag (`local` or `prod`)
2. `CV_RANKER_ENV` environment variable
3. Defaults to `local`

Once the environment is picked, pydantic-settings resolves each field with this priority:

1. Environment variables (e.g. `CV_RANKER_MODEL`)
2. The matching `config/<env>.env` dotenv file, if present (`config/local.env` or `config/prod.env`, auto-loaded — no manual `source` needed)
3. The field defaults below

| Env var                      | Local default               | Prod default                    |
|-------------------------------|------------------------------|----------------------------------|
| `CV_RANKER_BASE_URL`          | `http://localhost:11434/v1`  | `http://localhost:8000/v1`       |
| `CV_RANKER_API_KEY`           | `ollama`                     | `EMPTY`                          |
| `CV_RANKER_MODEL`             | `qwen3:14b`                  | `Qwen/Qwen3-14B`                 |
| `CV_RANKER_TIMEOUT_SECONDS`   | `90`                          | `120`                            |

Example config files are provided:

- [`config/local.env.example`](config/local.env.example)
- [`config/prod.env.example`](config/prod.env.example)

Copy and source the one you need (the real `config/local.env` / `config/prod.env` files are gitignored):

```bash
cp config/prod.env.example config/prod.env
# edit config/prod.env with your real vLLM URL/key/model
```

CLI flags always win over environment variables: `--model`, `--base-url`, `--api-key`, `--timeout`.

## Run

Local (Ollama, default — no flags needed beyond `--cv-folder`/`--requirements`):

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
PYTHONPATH=src python3 -m cv_ranker \
  --cv-folder tests/fixtures/cvs \
  --requirements "Minimum 5 years of experience, required skills: Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis" \
  --mode auto \
  --output text
```

Prod (vLLM):

```bash
cd /Users/vitaliesafronovici/Documents/work/dev/work/projects/python/ai-agent-cv-rank
PYTHONPATH=src python3 -m cv_ranker \
  --cv-folder tests/fixtures/cvs \
  --requirements "Minimum 5 years of experience, required skills: Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis" \
  --env prod \
  --mode auto \
  --output text
```

If the LLM server is not running, use deterministic mode:

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
- Both Ollama and vLLM are used through the same `cv_ranker.llm_client.LLMClient` (built on the `openai` SDK's `chat.completions.create`), so switching backends is a config change, not a code change.
- Reasoning models like `qwen3:14b` emit chain-of-thought tokens before the final answer, so per-candidate latency can be several seconds to ~1 minute depending on CV length; scoring many CVs in `llm`/`auto` mode runs sequentially and can take a while.
- For production use, you can improve scoring by adding weighted requirements and hard filters.




