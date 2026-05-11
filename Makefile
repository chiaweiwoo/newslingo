.PHONY: install test lint run reset-db help

# Install all deps including dev tools
install:
	uv sync --group dev
	uv run pre-commit install

# Run the full test suite
test:
	uv run pytest -v

# Run linter
lint:
	uv run ruff check .

# Fix auto-fixable lint issues
lint-fix:
	uv run ruff check . --fix

# Run the job locally (requires .env)
run:
	uv run job.py

# Reset DB tables (headlines, assessment_logs, prompt_rules, learning_digest)
# WARNING: destructive — clears all aggregated data
reset-db:
	@echo "This will delete all rows from headlines, assessment_logs, prompt_rules, and learning_digest."
	@read -p "Type 'yes' to confirm: " confirm; [ "$$confirm" = "yes" ] || (echo "Aborted." && exit 1)
	uv run python -c "\
from dotenv import load_dotenv; import os; load_dotenv(override=True); \
from supabase import create_client; \
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY')); \
[print(f'Deleted {t}:', len((sb.table(t).delete().neq('id','00000000-0000-0000-0000-000000000000') if t=='headlines' else sb.table(t).delete().gt('id',0)).execute().data or [])) for t in ('headlines','assessment_logs','prompt_rules','learning_digest')]"

help:
	@echo "Available targets:"
	@echo "  make install    — install deps + pre-commit hooks"
	@echo "  make test       — run pytest"
	@echo "  make lint       — run ruff linter"
	@echo "  make lint-fix   — auto-fix ruff issues"
	@echo "  make run        — run job.py locally"
	@echo "  make reset-db   — clear headlines/assessment_logs/prompt_rules (destructive)"
