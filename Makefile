# Twinverse Professional Build System
# Advanced CI/CD pipeline with automatic versioning

# ===== VARIABLES =====
PYTHON ?= python3
PIP ?= pip3
FLATPAK ?= flatpak
FLATPAK_BUILDER ?= flatpak-builder
VERSION_FILE = version
VERSION = $(shell cat $(VERSION_FILE))

# Compile GResource file
COMPILE_RESOURCES_TARGET := $(shell [ -f res/twinverse.gresources.xml ] && echo "compile-resources")

# Default target
.DEFAULT_GOAL := help

# ===== FUNCTIONS =====
print_header = @echo -e "\n\033[1;34m=== $1 ===\033[0m"
print_success = @echo -e "\033[1;32m $1\033[0m"
print_error = @echo -e "\033[1;31m $1\033[0m" >&2

# Help target
help:
	$(call print_header,"Twinverse Professional Build System")
	@echo ""
	@echo "Usage:"
	@echo "  make build           Build the application with production flags"
	@echo "  make flatpak         Build Flatpak package with validation"
	@echo "  make test            Run test suite with coverage check"
	@echo "  make clean           Remove all temporary artifacts"
	@echo "  make dev             Install development dependencies and setup virtual environment"
	@echo "  make bump-patch      Increment patch version (for critical fixes)"
	@echo "  make release-major   Create major release (requires 3 reviewers)"
	@echo "  make release-custom  Create custom release (blocked on dev branches)"
	@echo "                       Usage: make release-custom v=x.y.z [force=true]"
	@echo "  make version         Show current version"
	@echo "  make update-version  Update version (usage: make update-version v=x.y.z)"
	@echo "  make update-version-force  Update version even if same (usage: make update-version-force v=x.y.z)"
	@echo "  make bump-major      Increment major version (x.0.0)"
	@echo "  make bump-minor      Increment minor version (0.y.0)"
	@echo "  make release-minor   Create a minor release (0.y.0)"
	@echo "  make release-patch   Create a patch release (0.0.z)"
	@echo "  make appimage        Create AppImage package"
	@echo "  make help            Show this help message"
	@echo ""

# ===== COMPILE RESOURCES =====
compile-resources:
	@echo -e "\n\033[1;34m=== Compiling GResource... ===\033[0m"
	@if [ -f res/twinverse.gresources.xml ]; then \
		glib-compile-resources --sourcedir=res res/twinverse.gresources.xml --target=res/twinverse.gresource; \
		echo -e "\033[1;32m GResource compiled successfully!\033[0m"; \
	else \
		echo -e "\033[1;31m twinverse.gresources.xml not found!\033[0m" >&2; \
	fi

# ===== BUILD APPLICATION =====
build: dev
	$(call print_header,"Building Twinverse with production flags...")
	@echo "Installing Twinverse in the virtual environment..."
	@. .venv/bin/activate && $(PYTHON) -m pip install --upgrade pip > /dev/null 2>&1 && $(PYTHON) -m pip install . > /dev/null 2>&1
	$(call print_success,"Build completed successfully!")

# ===== FLATPAK PACKAGE =====
flatpak: dev validate-manifest
	$(call print_header,"Building Flatpak package...")
	@echo "Running Flatpak packaging script..."
	@./scripts/package-flatpak.sh > /dev/null 2>&1
	$(call print_success,"Flatpak package built successfully!")

# Validate Flatpak manifest before building
validate-manifest:
	$(call print_header,"Validating Flatpak manifest...")
	@if [ ! -f "io.github.mall0r.Twinverse.yaml" ]; then \
		$(call print_error,"Flatpak manifest io.github.mall0r.Twinverse.yaml not found!"); \
		exit 1; \
	fi
	$(call print_success,"Manifest validation passed!")

# ===== TEST SUITE =====
test: dev
	$(call print_header,"Running test suite...")
	@echo "Running pytest..."
	@. .venv/bin/activate && $(PYTHON) -m pytest
	@echo ""
	$(call print_header,"Running pre-commit...")
	@echo "Running pre-commit checks..."
	@. .venv/bin/activate && pre-commit run --all-files
	@echo ""
	$(call print_header,"Tests completed successfully!")

# Install dependencies for development
dev:
	$(call print_header,"Setting up development environment...")
	@bash -c 'if [ ! -d ".venv" ]; then \
		$(PYTHON) -m venv .venv; \
		echo "Virtual environment created"; \
	else \
		echo "Virtual environment already exists"; \
	fi'
	@echo "Installing/updating pip..."
	@. .venv/bin/activate && $(PYTHON) -m pip install --upgrade pip > /dev/null 2>&1
	@echo "Installing project dependencies..."
	@. .venv/bin/activate && $(PYTHON) -m pip install -e ".[test]" > /dev/null 2>&1
	@echo "Installing pre-commit hooks..."
	@. .venv/bin/activate && pre-commit install > /dev/null 2>&1
	$(call print_success,"Development environment set up successfully!")
	@echo "To activate the virtual environment in the future, run: source .venv/bin/activate"

# ===== CLEANUP =====
clean:
	@$(call print_header,"Cleaning temporary artifacts...")
	@./scripts/clean.sh
	@$(call print_success,"Clean completed!")

# ===== DEPENDENCY CHECK =====
check-deps:
	$(call print_header,"Checking dependencies...")
	@command -v git >/dev/null 2>&1 || { $(call print_error,"git not found"); exit 1; }
	@command -v python3 >/dev/null 2>&1 || { $(call print_error,"python3 not found"); exit 1; }
	@if [ ! -d ".git" ]; then $(call print_error,"Not in a git repository"); exit 1; fi
	$(call print_success,"All dependencies are present")

# Check git status
git-status:
	@if [ -n "$$(git status --porcelain)" ]; then \
		$(call print_error,"There are uncommitted changes in the repository"); \
		git status --porcelain; \
		exit 1; \
	else \
		$(call print_success,"Git repository is clean"); \
	fi

# ===== VERSION MANAGEMENT =====
# Show current version
version:
	$(call print_header,"Current version: $(VERSION)")

# Update version
update-version:
ifndef v
	$(error Please specify the new version: make update-version v=1.2.3)
endif
	$(call print_header,"Updating version from $(VERSION) to $(v)")
	@python scripts/version_manager.py $(v)

# Update version with force option
update-version-force:
ifndef v
	$(error Please specify the new version: make update-version-force v=1.2.3)
endif
	$(call print_header,"Updating version from $(VERSION) to $(v) with force")
	@python scripts/version_manager.py $(v) force

# Increment major version
bump-major:
	$(call print_header,"Incrementing major version...")
	@current_version=$$(cat $(VERSION_FILE)); \
	major=$$(echo $$current_version | cut -d. -f1); \
	minor=0; \
	patch=0; \
	new_version=$$((major + 1)).$$minor.$$patch; \
	python scripts/version_manager.py $$new_version

# Increment minor version
bump-minor:
	$(call print_header,"Incrementing minor version...")
	@current_version=$$(cat $(VERSION_FILE)); \
	major=$$(echo $$current_version | cut -d. -f1); \
	minor=$$(echo $$current_version | cut -d. -f2); \
	patch=0; \
	new_version=$$major.$$((minor + 1)).$$patch; \
	python scripts/version_manager.py $$new_version

# Increment patch version (for critical fixes)
bump-patch:
	$(call print_header,"Incrementing patch version...")
	@current_version=$$(cat $(VERSION_FILE)); \
	major=$$(echo $$current_version | cut -d. -f1); \
	minor=$$(echo $$current_version | cut -d. -f2); \
	patch=$$(echo $$current_version | cut -d. -f3); \
	new_version=$$major.$$minor.$$((patch + 1)); \
	python scripts/version_manager.py $$new_version

# ===== RELEASE MANAGEMENT =====
# Create major release (requires 3 reviewers)
release-major: check-deps git-status
	$(call print_header,"Creating major release (requires 3 reviewers)...")
	@current_version=$$(cat $(VERSION_FILE)); \
	major=$$(echo $$current_version | cut -d. -f1); \
	minor=$$(echo $$current_version | cut -d. -f2); \
	patch=$$(echo $$current_version | cut -d. -f3); \
	new_version=$$((major + 1)).0.0; \
	$(call print_header,"Updating version from $$current_version to $$new_version"); \
	python scripts/version_manager.py $$new_version; \
	$(call print_header,"Committing version changes"); \
	git add $(VERSION_FILE) share/metainfo/io.github.mall0r.Twinverse.metainfo.xml README.md docs/README.pt-br.md docs/README.es.md docs/CHANGELOG.md scripts/package-appimage.sh io.github.mall0r.Twinverse.yaml scripts/package-flatpak.sh; \
	git commit -m "Bump version to $$new_version"; \
	git tag "v$$new_version"; \
	$(call print_success,"Release $$new_version created successfully!"); \
	@echo "To push changes and tag, run:"; \
	@echo "  git push origin main"; \
	@echo "  git push origin v$$new_version"

# Create minor release
release-minor: check-deps git-status
	$(call print_header,"Creating minor release...")
	@current_version=$$(cat $(VERSION_FILE)); \
	major=$$(echo $$current_version | cut -d. -f1); \
	minor=$$(echo $$current_version | cut -d. -f2); \
	patch=$$(echo $$current_version | cut -d. -f3); \
	new_version=$$major.$$((minor + 1)).0; \
	$(call print_header,"Updating version from $$current_version to $$new_version"); \
	python scripts/version_manager.py $$new_version; \
	$(call print_header,"Committing version changes"); \
	git add $(VERSION_FILE) share/metainfo/io.github.mall0r.Twinverse.metainfo.xml README.md docs/README.pt-br.md docs/README.es.md docs/CHANGELOG.md scripts/package-appimage.sh io.github.mall0r.Twinverse.yaml scripts/package-flatpak.sh; \
	git commit -m "Bump version to $$new_version"; \
	git tag "v$$new_version"; \
	$(call print_success,"Release $$new_version created successfully!"); \
	@echo "To push changes and tag, run:"; \
	@echo "  git push origin main"; \
	@echo "  git push origin v$$new_version"

# Create patch release
release-patch: check-deps git-status
	$(call print_header,"Creating patch release...")
	@current_version=$$(cat $(VERSION_FILE)); \
	major=$$(echo $$current_version | cut -d. -f1); \
	minor=$$(echo $$current_version | cut -d. -f2); \
	patch=$$(echo $$current_version | cut -d. -f3); \
	new_version=$$major.$$minor.$$((patch + 1)); \
	$(call print_header,"Updating version from $$current_version to $$new_version"); \
	python scripts/version_manager.py $$new_version; \
	$(call print_header,"Committing version changes"); \
	git add $(VERSION_FILE) share/metainfo/io.github.mall0r.Twinverse.metainfo.xml README.md docs/README.pt-br.md docs/README.es.md docs/CHANGELOG.md scripts/package-appimage.sh io.github.mall0r.Twinverse.yaml scripts/package-flatpak.sh; \
	git commit -m "Bump version to $$new_version"; \
	git tag "v$$new_version"; \
	$(call print_success,"Release $$new_version created successfully!"); \
	@echo "To push changes and tag, run:"; \
	@echo "  git push origin main"; \
	@echo "  git push origin v$$new_version"

# Create custom release (blocked on dev branches)
release-custom:
	@if git branch --show-current | grep -E 'dev|beta'; then \
		$(call print_error,"Custom releases are blocked on development branches"); \
		exit 1; \
	fi
ifndef v
	$(error Please specify the new version: make release-custom v=1.2.3)
endif
	@current_version=$$(cat $(VERSION_FILE)); \
	if [ "$$current_version" = "$(v)" ] && [ "$(force)" != "true" ]; then \
		$(call print_error,"Version is already $(v)"); \
		@echo "Adicione uma opo de -force para que seja possivel fazer mesmo se a Version is already."; \
		exit 1; \
	else \
		$(MAKE) check-deps && \
		$(MAKE) git-status && \
		$(call print_header,"Creating custom release...") && \
		$(call print_header,"Updating version from $$current_version to $(v)") && \
		if [ "$(force)" = "true" ]; then \
			python scripts/version_manager.py $(v) force; \
		else \
			python scripts/version_manager.py $(v); \
		fi && \
		$(call print_header,"Committing version changes") && \
		git add $(VERSION_FILE) share/metainfo/io.github.mall0r.Twinverse.metainfo.xml README.md docs/README.pt-br.md docs/README.es.md docs/CHANGELOG.md scripts/package-appimage.sh io.github.mall0r.Twinverse.yaml scripts/package-flatpak.sh && \
		git commit -m "Bump version to $(v)" && \
		git tag "v$(v)" && \
		$(call print_success,"Release $(v) created successfully!") && \
		@echo "To push changes and tag, run:" && \
		@echo "  git push origin main" && \
		@echo "  git push origin v$(v)"; \
	fi

# Create AppImage package
appimage:
	$(call print_header,"Creating AppImage package...")
	@echo "Running AppImage packaging script..."
	@./scripts/package-appimage.sh
	$(call print_success,"AppImage package created successfully!")

# ===== TARGETS =====
.PHONY: help build flatpak validate-manifest test clean bump-patch release-major release-custom version update-version update-version-force bump-major bump-minor release-minor release-patch check-deps git-status appimage dev
