"""
Test to ensure manifest.json has correct absolute paths for chat app.

This prevents 404 errors when browsers try to load PWA icons.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_manifest_has_absolute_paths():
    """Verify manifest.json uses absolute /chat/ paths for all icon resources."""
    manifest_path = Path(__file__).parent.parent / "static" / "chat" / "manifest.json"
    
    assert manifest_path.exists(), f"Manifest not found at {manifest_path}"
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    # Check icon paths are absolute
    assert "icons" in manifest, "Manifest missing icons field"
    
    for icon in manifest["icons"]:
        src = icon.get("src", "")
        assert src.startswith("/chat/"), (
            f"Icon src '{src}' should start with '/chat/' to prevent 404 errors. "
            f"Relative paths in manifest.json are resolved relative to the document URL, "
            f"not the manifest URL, causing 404s."
        )
    
    # Check start_url is absolute
    start_url = manifest.get("start_url", "")
    assert start_url.startswith("/chat/") or start_url == "/chat", (
        f"start_url '{start_url}' should be '/chat/' for absolute path"
    )


def test_manifest_source_matches_deployed():
    """Ensure source manifest.json matches deployed version."""
    source_manifest = Path(__file__).parent.parent / "monitoring" / "dashboard" / "chat-frontend" / "public" / "manifest.json"
    deployed_manifest = Path(__file__).parent.parent / "static" / "chat" / "manifest.json"
    
    assert source_manifest.exists(), f"Source manifest not found at {source_manifest}"
    assert deployed_manifest.exists(), f"Deployed manifest not found at {deployed_manifest}"
    
    with open(source_manifest) as f:
        source_data = json.load(f)
    
    with open(deployed_manifest) as f:
        deployed_data = json.load(f)
    
    # Both should have absolute paths
    assert source_data == deployed_data, (
        "Source and deployed manifest.json should match. "
        "Run './deploy.sh chat' to rebuild and deploy."
    )
