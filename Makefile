.PHONY: setup check-pixi check-copier check-act check-gh check-snapper install-hooks lint format format-notebooks typecheck test

# Every check-* target only reports a missing tool and the command to install it;
# none of them install anything on your behalf. `make setup` runs all of them
# upfront, so a missing tool is one clear message, not a cryptic failure deep
# inside a later command. See project-meta/docs/tooling.md.

setup: check-pixi
	@ok=1; \
	$(MAKE) --no-print-directory check-copier || ok=0; \
	$(MAKE) --no-print-directory check-act || true; \
	$(MAKE) --no-print-directory check-gh || true; \
	$(MAKE) --no-print-directory check-snapper || ok=0; \
	if [ "$$ok" = "0" ]; then \
		echo ""; \
		echo "Install the missing tool(s) above, then re-run 'make setup'."; \
		exit 1; \
	fi
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
		echo "copier not found. Install: pixi global install copier"; \
		exit 1; \
	}

check-act:
	@command -v act >/dev/null 2>&1 || { \
		echo "act not found (optional, only needed for local CI preview). Install: pixi global install act"; \
	}

check-gh:
	@command -v gh >/dev/null 2>&1 || { \
		echo "gh not found (optional, only needed for GitHub CLI convenience). Install: pixi global install gh"; \
	}

check-snapper:
	@command -v snapper >/dev/null 2>&1 || { \
		echo "snapper not found. The markdown pre-commit hook assumes it is already"; \
		echo "installed, rather than building it from source on every machine."; \
		echo "Install: pixi global install snapper-fmt"; \
		exit 1; \
	}

install-hooks: check-pixi check-snapper
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
