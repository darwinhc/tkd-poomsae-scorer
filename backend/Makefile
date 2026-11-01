SHELL := /bin/bash

# Project packaging variables.
APP_NAME := PoomsaeServer
SPEC_FILE := packaging/pyinstaller/$(APP_NAME).spec
PYTHON := $(shell if [ -x ./venv/bin/python ]; then echo ./venv/bin/python; elif [ -x ./.venv/bin/python ]; then echo ./.venv/bin/python; else echo python; fi)
PYINSTALLER := $(PYTHON) -m PyInstaller
BUILD_DIR := build/pyinstaller
DIST_ROOT := dist
RUNTIME_DIR := packaging/runtime

# PyInstaller output goes to the build directory so it never collides with the
# delivery bundle folder (which uses the same name as the executable folder).
WINDOWS_BUILD_DIST := $(BUILD_DIR)/windows/dist
WINDOWS_DIST := $(DIST_ROOT)/windows
WINDOWS_PACKAGE := $(WINDOWS_DIST)/$(APP_NAME)

LINUX_BUILD_DIST := $(BUILD_DIR)/linux/dist
LINUX_DIST := $(DIST_ROOT)/linux
LINUX_PACKAGE := $(LINUX_DIST)/$(APP_NAME)

.PHONY: help clean css package-windows package-linux package-all

help: ## List available commands
	@echo "Available targets:"
	@echo "  make css              - Rebuild the offline admin CSS (needs Node.js)"
	@echo "  make clean            - Remove packaging artifacts"
	@echo "  make package-linux    - Build the Linux delivery bundle (Linux only)"
	@echo "  make package-windows  - Build the Windows delivery bundle (Windows/MSYS only)"
	@echo "  make package-all      - Try to package both targets (no cross-compilation)"

clean: ## Remove build and dist artifacts
	@echo "Cleaning artifacts..."
	rm -rf build dist
	rm -rf __pycache__ .pytest_cache .ruff_cache

css: ## Rebuild the offline Tailwind CSS for the admin panel and TV scoreboard
	cd assets && npm install --no-audit --no-fund && npm run build:css

package-linux: ## Build Linux executable delivery bundle
	@OS_NAME="$$(uname -s)"; \
	if [[ "$$OS_NAME" != "Linux" ]]; then \
		echo "[ERROR] package-linux must run on Linux. Detected OS: $$OS_NAME"; \
		exit 1; \
	fi
	@echo "Packaging Linux build with PyInstaller..."
	$(PYINSTALLER) --noconfirm --clean --distpath "$(LINUX_BUILD_DIST)" --workpath "$(BUILD_DIR)/linux/work" "$(SPEC_FILE)"
	@echo "Assembling Linux delivery folder..."
	rm -rf "$(LINUX_PACKAGE)"
	mkdir -p "$(LINUX_PACKAGE)/config" "$(LINUX_PACKAGE)/data" "$(LINUX_PACKAGE)/logs"
	cp -R "$(LINUX_BUILD_DIST)/$(APP_NAME)" "$(LINUX_PACKAGE)/$(APP_NAME)"
	cp "$(RUNTIME_DIR)/.env.example" "$(LINUX_PACKAGE)/.env"
	cp "$(RUNTIME_DIR)/config/poomsae_categories.yaml" "$(LINUX_PACKAGE)/config/poomsae_categories.yaml"
	cp "$(RUNTIME_DIR)/OPERATIONS.txt" "$(LINUX_PACKAGE)/OPERATIONS.txt"
	cp "$(RUNTIME_DIR)/start_admin_panel.sh" "$(LINUX_PACKAGE)/start_admin_panel.sh"
	chmod +x "$(LINUX_PACKAGE)/start_admin_panel.sh"
	@echo "Linux delivery ready at: $(LINUX_PACKAGE)"

package-windows: ## Build Windows executable delivery bundle
	@OS_NAME="$$(uname -s)"; \
	case "$$OS_NAME" in \
		MINGW*|MSYS*|CYGWIN*|Windows_NT) ;; \
		*) echo "[ERROR] package-windows must run on Windows/MSYS. Detected OS: $$OS_NAME"; exit 1 ;; \
	esac
	@echo "Packaging Windows build with PyInstaller..."
	$(PYINSTALLER) --noconfirm --clean --distpath "$(WINDOWS_BUILD_DIST)" --workpath "$(BUILD_DIR)/windows/work" "$(SPEC_FILE)"
	@echo "Assembling Windows delivery folder..."
	rm -rf "$(WINDOWS_PACKAGE)"
	mkdir -p "$(WINDOWS_PACKAGE)/config" "$(WINDOWS_PACKAGE)/data" "$(WINDOWS_PACKAGE)/logs"
	cp -R "$(WINDOWS_BUILD_DIST)/$(APP_NAME)" "$(WINDOWS_PACKAGE)/$(APP_NAME)"
	cp "$(RUNTIME_DIR)/.env.example" "$(WINDOWS_PACKAGE)/.env"
	cp "$(RUNTIME_DIR)/config/poomsae_categories.yaml" "$(WINDOWS_PACKAGE)/config/poomsae_categories.yaml"
	cp "$(RUNTIME_DIR)/OPERATIONS.txt" "$(WINDOWS_PACKAGE)/OPERATIONS.txt"
	cp "$(RUNTIME_DIR)/Start Admin Panel.bat" "$(WINDOWS_PACKAGE)/Start Admin Panel.bat"
	@echo "Windows delivery ready at: $(WINDOWS_PACKAGE)"

package-all: ## Try both package targets sequentially (no cross-compilation)
	@echo "Starting package-all..."
	-$(MAKE) package-linux
	-$(MAKE) package-windows
	@echo "Note: PyInstaller does not support cross-compiling between Linux and Windows."
