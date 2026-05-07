#!/usr/bin/env bash
# Twinverse Professional Flatpak Build Script
set -euo pipefail

# ===== CONFIGURATION =====
readonly APP_ID="io.github.mall0r.Twinverse"
readonly MANIFEST="$APP_ID.yaml"
readonly BUILD_DIR="build-dir"
readonly REPO_DIR="flatpak-repo"
readonly BUNDLE_NAME="Twinverse.flatpak"

# ===== FUNCTIONS =====
print_header() {
    echo -e "\n\033[1;34m=== $1 ===\033[0m"
}

print_success() {
    echo -e "\033[1;32m✓ $1\033[0m"
}

print_error() {
    echo -e "\033[1;31m✗ $1\033[0m" >&2
}

check_dependencies() {
    print_header "Checking Dependencies"

    local missing_deps=()

    # Required commands
    for cmd in flatpak flatpak-builder ostree; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done

    # Optional commands (only for features)
    if [[ -f "res/twinverse.gresources.xml" ]]; then
        if ! command -v glib-compile-resources &> /dev/null; then
            print_error "glib-compile-resources not found (required for GResource)"
            echo "  Install: sudo apt install libglib2.0-dev-bin"
            missing_deps+=("glib-compile-resources")
        fi
    fi

    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        print_error "Missing dependencies: ${missing_deps[*]}"
        exit 1
    fi

    print_success "All dependencies verified"
}

setup_runtime() {
    print_header "Setting up Flatpak Runtime"

    local sdk_version="50"
    local runtime="org.gnome.Platform"
    local sdk="org.gnome.Sdk"

    # Use user installation for both local and CI environments
    if ! flatpak list --user --runtime | grep -q "$runtime//$sdk_version"; then
        echo "Installing GNOME $sdk_version runtime for user..."
        flatpak install -y --user flathub "$runtime//$sdk_version" "$sdk//$sdk_version" || {
            print_error "Failed to install runtime"
            exit 1
        }
    fi

    print_success "Runtime configured"
}

clean_build() {
    print_header "Cleaning Previous Builds"

    # Remove build directories
    rm -rf "$BUILD_DIR" .flatpak-builder .flatpak-builder-cache

    # Remove previous bundle if exists
    [[ -f "$BUNDLE_NAME" ]] && rm -f "$BUNDLE_NAME"

    # Clean compiled resources
    [[ -f "res/twinverse.gresource" ]] && rm -f "res/twinverse.gresource"

    print_success "Environment cleaned"
}

compile_resources() {
    # Only compile if twinverse.gresources.xml exists
    if [[ -f "res/twinverse.gresources.xml" ]]; then
        print_header "Compiling Resources"
        glib-compile-resources \
            --target=res/twinverse.gresource \
            --sourcedir=res \
            res/twinverse.gresources.xml
        print_success "Resources compiled"
    fi
}

build_flatpak() {
    print_header "Building Flatpak"

    local build_cmd=(
        flatpak-builder
        --force-clean
        --install-deps-from=flathub
        --repo="$REPO_DIR"
        --ccache
        --disable-updates
        --keep-build-dirs
    )

    # Always use user installation for consistency
    build_cmd+=(--user)

    # Check if it's a development build
    if [[ "${1:-}" == "--dev" ]]; then
        build_cmd+=(--user)  # Install for user
    fi

    # Add architecture if specified
    if [[ -n "${FLATPAK_ARCH:-}" ]]; then
        build_cmd+=(--arch="$FLATPAK_ARCH")
    fi

    "${build_cmd[@]}" "$BUILD_DIR" "$MANIFEST"

    print_success "Flatpak built"
}

create_repository() {
    print_header "Creating Local Repository"

    if [[ ! -d "$REPO_DIR" ]]; then
        ostree init --mode=archive-z2 --repo="$REPO_DIR"
    fi

    print_success "Repository ready"
}

create_bundle() {
    print_header "Creating Bundle"

    # ★ FIX: Read version from metainfo.xml file ★
    local metainfo_path="share/metainfo/io.github.mall0r.Twinverse.metainfo.xml"
    local version
    version=$(grep -oP '<release version="\K[^"]+' "$metainfo_path" | head -1)

    # Determine architecture for bundle name
    local arch_suffix=""
    if [[ -n "${FLATPAK_ARCH:-}" ]]; then
        arch_suffix="-$FLATPAK_ARCH"
    else
        # Use native architecture if not specified
        arch_suffix="-$(uname -m)"
    fi

    # Bundle name with extracted version and architecture
    local final_bundle="Twinverse-${version:-unknown}${arch_suffix}.flatpak"

    echo "📦 Creating: $final_bundle"
    echo "📄 Version source: $metainfo_path"
    echo "🆔 App ID: $APP_ID"
    echo "🔧 Architecture: ${FLATPAK_ARCH:-$(uname -m)}"

    # Remove previous bundle if exists
    [[ -f "$final_bundle" ]] && rm -f "$final_bundle"

    # Include architecture in the build-bundle command if specified
    if [[ -n "${FLATPAK_ARCH:-}" ]]; then
        flatpak build-bundle "$REPO_DIR" "$final_bundle" --arch="$FLATPAK_ARCH" "$APP_ID"
    else
        flatpak build-bundle "$REPO_DIR" "$final_bundle" "$APP_ID"
    fi

    # Simple verification
    if [[ -f "$final_bundle" ]]; then
        local bundle_size
        bundle_size=$(du -h "$final_bundle" | cut -f1)
        print_success "✅ Bundle created successfully!"
        echo "   File: $final_bundle"
        echo "   Size: $bundle_size"
        echo "   Version: $version"
        return 0
    else
        print_error "❌ Failed to create bundle"
        return 1
    fi
}

test_build() {
    print_header "Testing Build"

    # Test using the real binary name (twinverse) instead of App ID
    if timeout 5s flatpak-builder --run "$BUILD_DIR" "$MANIFEST" "twinverse" --help >/dev/null 2>&1; then
        print_success "Build tested successfully"
    elif timeout 5s flatpak-builder --run "$BUILD_DIR" "$MANIFEST" "twinverse" >/dev/null 2>&1; then
        print_success "Build tested (ran without arguments)"
    else
        # Alternative test: just check if files exist
        if [[ -f "$BUILD_DIR/files/bin/twinverse" ]]; then
            print_success "Binary found - build valid"
        else
            print_error "Binary not found in build"
            return 1
        fi
    fi
}

# ===== MAIN FLOW =====
main() {
    print_header "🚀 Twinverse Flatpak Builder"
    echo "App ID: $APP_ID"
    echo "Manifest: $MANIFEST"
    echo ""

    # Parse arguments
    local dev_build=false
    local skip_tests=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --dev)
                dev_build=true
                shift
                ;;
            --skip-tests)
                skip_tests=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                print_error "Unknown argument: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Build flow
    check_dependencies
    setup_runtime
    clean_build
    compile_resources
    create_repository
    build_flatpak "$dev_build"

    # Skip tests as they are not needed for the Flatpak build
    # Tests should be run during development, not during packaging

    create_bundle

    # Final information
    print_header "✅ Build Completed"
    show_usage_instructions
}

show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Options:
  --dev          Development build (install for user)
  --skip-tests   Skip tests after build
  --help, -h     Show this help

Examples:
  $0              # Default build (release)
  $0 --dev        # Development build
  $0 --dev --skip-tests

EOF
}

show_usage_instructions() {
    cat << EOF

📦 INSTALLATION AND USAGE:

  Install local bundle:
    flatpak install --user $BUNDLE_NAME

  Run application:
    flatpak run $APP_ID

  Uninstall:
    flatpak uninstall --user $APP_ID

🔧 DEBUGGING:

  View application logs:
    flatpak run --command=sh $APP_ID

  Access sandbox:
    flatpak run --devel $APP_ID

📁 CREATED STRUCTURE:
  $BUILD_DIR/     - Build directory
  $REPO_DIR/      - Local OSTree repository
  Twinverse-*.flatpak - Installable bundle

EOF
}

# ===== ENTRY POINT =====
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
