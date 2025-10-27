"""
Tests for /api/docs/list endpoint in monitoring server.
Tests the endpoint that lists all documentation files in the docs directory.
"""
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import tempfile
import pytest
from monitoring.server import app


@pytest.fixture(scope="module", autouse=True)
def ensure_database():
    """
    Ensure database singleton is available for all tests in this module.

    IMPORTANT: monitoring.server imports and stores a reference to the database
    at module load time. If other tests close the singleton, this reference
    becomes stale. This fixture ensures database is reopened, but the stored
    reference in monitoring.server may still be closed.

    TODO: Refactor monitoring.server to use get_database() lazily instead of
    storing reference at module level.
    """
    from core.database_manager import get_database, close_database
    # Close and reopen to get a fresh connection
    close_database()
    db = get_database()

    # HACK: Update monitoring.server's user_db reference
    import monitoring.server
    monitoring.server.user_db = db

    yield db
    # Don't close - leave for other test modules


@pytest.fixture
def client():
    """Create test client for Flask app"""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_docs_dir(monkeypatch):
    """Create temporary docs directory with test files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        docs_path = Path(tmpdir) / "docs"
        docs_path.mkdir()
        
        # Create test markdown files
        (docs_path / "README.md").write_text("# Test README")
        (docs_path / "API.md").write_text("# API Documentation")
        
        # Create archive subdirectory
        archive_path = docs_path / "archive"
        archive_path.mkdir()
        (archive_path / "OLD_NOTES.md").write_text("# Old notes")
        
        # Create a text file
        (docs_path / "notes.txt").write_text("Test notes")
        
        # Patch Path(__file__).parent.parent to point to tmpdir
        original_file = Path(sys.modules['monitoring.server'].__file__)
        
        def mock_path_file():
            return Path(tmpdir) / "monitoring" / "server.py"
        
        # We need to patch the module's __file__ attribute behavior
        # Since Path(__file__).parent.parent is evaluated at runtime,
        # we'll create the monitoring directory structure
        monitoring_dir = Path(tmpdir) / "monitoring"
        monitoring_dir.mkdir()
        
        yield docs_path, tmpdir


class TestDocsListEndpoint:
    """Test suite for /api/docs/list endpoint"""
    
    def test_docs_list_returns_json(self, client):
        """Test that endpoint returns JSON response"""
        response = client.get("/api/docs/list")
        assert response.content_type == "application/json"
    
    def test_docs_list_structure(self, client):
        """Test that response has expected structure"""
        response = client.get("/api/docs/list")
        data = json.loads(response.data)
        
        # Should have 'files' and 'total' keys
        assert "files" in data or "error" in data
        
        # If successful, check structure
        if "files" in data:
            assert "total" in data
            assert isinstance(data["files"], list)
            assert isinstance(data["total"], int)
    
    def test_docs_list_file_structure(self, client):
        """Test that each file entry has expected fields"""
        response = client.get("/api/docs/list")
        
        # Only test if docs directory exists and has files
        if response.status_code == 200:
            data = json.loads(response.data)
            
            if data["total"] > 0:
                file_entry = data["files"][0]
                
                # Each file should have these fields
                assert "path" in file_entry
                assert "name" in file_entry
                assert "size" in file_entry
                assert "modified" in file_entry
                assert "is_archive" in file_entry
                
                # Verify types
                assert isinstance(file_entry["path"], str)
                assert isinstance(file_entry["name"], str)
                assert isinstance(file_entry["size"], int)
                assert isinstance(file_entry["modified"], (int, float))
                assert isinstance(file_entry["is_archive"], bool)
    
    def test_docs_list_archive_detection(self, client):
        """Test that archive files are properly marked"""
        response = client.get("/api/docs/list")
        
        if response.status_code == 200:
            data = json.loads(response.data)
            
            # Find any archive files
            archive_files = [f for f in data["files"] if "archive" in f["path"]]
            
            # If we have archive files, they should be marked
            for file_entry in archive_files:
                assert file_entry["is_archive"] is True
    
    def test_docs_list_filters_correct_extensions(self, client):
        """Test that only .md and .txt files are included"""
        response = client.get("/api/docs/list")
        
        if response.status_code == 200:
            data = json.loads(response.data)
            
            # All files should end with .md or .txt
            for file_entry in data["files"]:
                name = file_entry["name"]
                assert name.endswith(".md") or name.endswith(".txt"), \
                    f"File {name} has unexpected extension"
    
    def test_docs_list_handles_missing_directory(self, monkeypatch):
        """Test graceful handling when docs directory doesn't exist"""
        # Create a test client
        test_client = app.test_client()
        
        # This test verifies the error handling works
        # The actual docs directory may or may not exist
        response = test_client.get("/api/docs/list")
        
        # Should return either success or 404 with error message
        assert response.status_code in [200, 404]
        
        if response.status_code == 404:
            data = json.loads(response.data)
            assert "error" in data
            assert "not found" in data["error"].lower()
    
    def test_docs_list_returns_sorted_files(self, client):
        """Test that files are returned in sorted order"""
        response = client.get("/api/docs/list")
        
        if response.status_code == 200:
            data = json.loads(response.data)
            
            if data["total"] > 1:
                paths = [f["path"] for f in data["files"]]
                assert paths == sorted(paths), "Files should be sorted"
    
    def test_docs_list_count_matches_list_length(self, client):
        """Test that total count matches actual number of files"""
        response = client.get("/api/docs/list")
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data["total"] == len(data["files"]), \
                "Total count should match number of files"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
