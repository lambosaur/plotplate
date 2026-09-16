.PHONY: setup check-pixi check-copier check-act check-gh install-hooks lint format format-notebooks typecheck test

# Every check-* target is a no-op if the tool is already present, so `make setup`
# is always safe to re-run; it only fills in whatever is missing. See
# project-meta/docs/tooling.md.

setup: check-pixi
	pixi install -e dev
	@echo ""
	@read -p "Install pre-commit hooks now? [y/N] " ans; \
	if [ "$$ans" = "y" ] || [ "$$ans" = "Y" ]; then $(MAKE) install-hooks; fi
	@echo "Setup done. Run 'make lint test' to check everything works."

check-pixi:
	@command -v pixi >/dev/null 2>&1 || { \
		echo "pixi not found. Install: curl -fsSL https://pixi.sh/install.sh | bash"; \
		exit 1; \
	}

check-copier:
	@command -v copier >/dev/null 2>&1 || { \
		echo "copier not found. Installing via 'pixi global install copier'..."; \
		pixi global install copier; \
	}

check-act:
	@command -v act >/dev/null 2>&1 || { \
		echo "act not found. Installing via 'pixi global install act'..."; \
		pixi global install act; \
	}

check-gh:
	@command -v gh >/dev/null 2>&1 || { \
		echo "gh not found. Installing via 'pixi global install gh'..."; \
		pixi global install gh; \
	}

install-hooks: check-pixi
	pixi run -e dev pre-commit install

lint: check-pixi
	pixi run -e dev ruff check .
	pixi run -e dev lint-toml
	pixi run -e dev lint-yaml
	# markdownlint-cli2/typos/editorconfig-checker run through pre-commit, which manages
	# their own (non-pixi) toolchains; see project-meta/docs/tooling.md.
	pixi run -e dev pre-commit run markdownlint-cli2 --all-files
	pixi run -e dev pre-commit run mdformat --all-files
	pixi run -e dev pre-commit run typos --all-files
	pixi run -e dev pre-commit run editorconfig-checker --all-files

format: check-pixi
	pixi run -e dev ruff format .
	pixi run -e dev format-md
	pixi run -e dev format-toml

format-notebooks: check-pixi
	pixi run -e jupyter format-notebooks

typecheck: check-pixi
	pixi run -e dev mypy .

test: check-pixi
	pixi run -e dev pytest
