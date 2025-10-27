"""
Unit tests for document tracking functionality
Tests the SQLite-based document status tracking system
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import tempfile
from datetime import datetime

import pytest

from tasks.database import Database


class TestDocumentTracking:
    """Test document tracking operations in Database"""

    @pytest.fixture
    def db(self):
        """Create a temporary database for testing"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        # Create database with schema
        database = Database(db_path)
        yield database

        # Cleanup
        database.close()
        Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_create_document(self, db):
        """Test creating a new document record"""
        # Create a task first (required by foreign key constraint)
        await db.create_task(
            task_id="test123",
            user_id=12345,
            description="Test task",
            workspace="/tmp/test",
        )

        doc = await db.create_document("test/doc.md", task_id="test123")

        assert doc is not None
        assert doc["path"] == "test/doc.md"
        assert doc["status"] == "active"
        assert doc["task_id"] == "test123"
        assert doc["created_at"] is not None
        assert doc["updated_at"] is not None
        assert doc["archived_at"] is None

    @pytest.mark.asyncio
    async def test_create_document_without_task(self, db):
        """Test creating a document without task association"""
        doc = await db.create_document("standalone.md")

        assert doc is not None
        assert doc["path"] == "standalone.md"
        assert doc["status"] == "active"
        assert doc["task_id"] is None

    @pytest.mark.asyncio
    async def test_create_duplicate_document(self, db):
        """Test that creating duplicate document returns existing record"""
        doc1 = await db.create_document("duplicate.md")
        doc2 = await db.create_document("duplicate.md")

        assert doc1["id"] == doc2["id"]
        assert doc1["path"] == doc2["path"]

    def test_get_document(self, db):
        """Test retrieving a document by path"""
        # Create a task first
        asyncio.run(db.create_task(
            task_id="task456",
            user_id=12345,
            description="Test task",
            workspace="/tmp/test",
        ))

        # Create document
        asyncio.run(db.create_document("fetch/doc.md", task_id="task456"))

        # Retrieve it
        doc = db.get_document("fetch/doc.md")

        assert doc is not None
        assert doc["path"] == "fetch/doc.md"
        assert doc["task_id"] == "task456"

    def test_get_nonexistent_document(self, db):
        """Test retrieving a document that doesn't exist"""
        doc = db.get_document("nonexistent.md")
        assert doc is None

    def test_list_documents(self, db):
        """Test listing all documents"""
        # Create multiple documents
        asyncio.run(db.create_document("doc1.md"))
        asyncio.run(db.create_document("doc2.md"))
        asyncio.run(db.create_document("doc3.md"))

        docs = db.list_documents()

        assert len(docs) == 3
        paths = [doc["path"] for doc in docs]
        assert "doc1.md" in paths
        assert "doc2.md" in paths
        assert "doc3.md" in paths

    def test_list_documents_by_status(self, db):
        """Test filtering documents by status"""
        # Create documents with different statuses
        asyncio.run(db.create_document("active1.md"))
        asyncio.run(db.create_document("active2.md"))
        asyncio.run(db.create_document("archived.md"))
        asyncio.run(db.update_document_status("archived.md", "archived"))

        # List only active documents
        active_docs = db.list_documents(status="active")
        assert len(active_docs) == 2

        # List only archived documents
        archived_docs = db.list_documents(status="archived")
        assert len(archived_docs) == 1
        assert archived_docs[0]["path"] == "archived.md"

    @pytest.mark.asyncio
    async def test_update_document_status_to_archived(self, db):
        """Test archiving a document"""
        # Create document
        await db.create_document("to_archive.md")

        # Archive it
        result = await db.update_document_status("to_archive.md", "archived", notes="No longer needed")

        assert result is True

        # Verify status change
        doc = db.get_document("to_archive.md")
        assert doc["status"] == "archived"
        assert doc["archived_at"] is not None
        assert doc["notes"] == "No longer needed"

    @pytest.mark.asyncio
    async def test_update_document_status_to_active(self, db):
        """Test restoring an archived document"""
        # Create and archive document
        await db.create_document("to_restore.md")
        await db.update_document_status("to_restore.md", "archived")

        # Restore it
        result = await db.update_document_status("to_restore.md", "active", notes="Needed again")

        assert result is True

        # Verify status change
        doc = db.get_document("to_restore.md")
        assert doc["status"] == "active"
        assert doc["archived_at"] is None  # Cleared when restoring
        assert doc["notes"] == "Needed again"

    @pytest.mark.asyncio
    async def test_update_nonexistent_document(self, db):
        """Test updating a document that doesn't exist"""
        result = await db.update_document_status("nonexistent.md", "archived")
        assert result is False

    def test_get_documents_by_task(self, db):
        """Test retrieving all documents for a task"""
        # Create tasks first
        asyncio.run(db.create_task(
            task_id="task1",
            user_id=12345,
            description="Task 1",
            workspace="/tmp/test",
        ))
        asyncio.run(db.create_task(
            task_id="task2",
            user_id=12345,
            description="Task 2",
            workspace="/tmp/test",
        ))

        # Create documents for different tasks
        asyncio.run(db.create_document("task1_doc1.md", task_id="task1"))
        asyncio.run(db.create_document("task1_doc2.md", task_id="task1"))
        asyncio.run(db.create_document("task2_doc1.md", task_id="task2"))

        # Get documents for task1
        task1_docs = db.get_documents_by_task("task1")

        assert len(task1_docs) == 2
        paths = [doc["path"] for doc in task1_docs]
        assert "task1_doc1.md" in paths
        assert "task1_doc2.md" in paths

    def test_get_documents_by_nonexistent_task(self, db):
        """Test retrieving documents for a task with no documents"""
        docs = db.get_documents_by_task("nonexistent_task")
        assert len(docs) == 0

    def test_get_document_statistics(self, db):
        """Test document statistics aggregation"""
        # Create documents with different statuses
        asyncio.run(db.create_document("active1.md"))
        asyncio.run(db.create_document("active2.md"))
        asyncio.run(db.create_document("archived1.md"))
        asyncio.run(db.update_document_status("archived1.md", "archived"))
        asyncio.run(db.create_document("archived2.md"))
        asyncio.run(db.update_document_status("archived2.md", "archived"))

        stats = db.get_document_statistics()

        assert stats["total_documents"] == 4
        assert stats["by_status"]["active"] == 2
        assert stats["by_status"]["archived"] == 2
        assert "recently_archived" in stats

    def test_document_timestamps(self, db):
        """Test that timestamps are properly set"""
        # Create document
        before = datetime.now().isoformat()
        doc = asyncio.run(db.create_document("timestamp_test.md"))
        after = datetime.now().isoformat()

        assert doc["created_at"] >= before
        assert doc["created_at"] <= after
        assert doc["updated_at"] >= before
        assert doc["updated_at"] <= after

    @pytest.mark.asyncio
    async def test_document_notes(self, db):
        """Test updating document notes"""
        await db.create_document("notes_test.md")

        # Update with notes
        await db.update_document_status("notes_test.md", "archived", notes="Test note")

        doc = db.get_document("notes_test.md")
        assert doc["notes"] == "Test note"

        # Update notes again
        await db.update_document_status("notes_test.md", "active", notes="Updated note")

        doc = db.get_document("notes_test.md")
        assert doc["notes"] == "Updated note"

    def test_document_status_transitions(self, db):
        """Test various status transitions"""
        # Create document
        asyncio.run(db.create_document("transitions.md"))

        # active -> archived
        asyncio.run(db.update_document_status("transitions.md", "archived"))
        doc = db.get_document("transitions.md")
        assert doc["status"] == "archived"
        assert doc["archived_at"] is not None

        # archived -> active
        asyncio.run(db.update_document_status("transitions.md", "active"))
        doc = db.get_document("transitions.md")
        assert doc["status"] == "active"
        assert doc["archived_at"] is None

        # active -> deleted
        asyncio.run(db.update_document_status("transitions.md", "deleted"))
        doc = db.get_document("transitions.md")
        assert doc["status"] == "deleted"
        assert doc["archived_at"] is None

    def test_list_all_statuses(self, db):
        """Test listing documents without status filter"""
        # Create documents with different statuses
        asyncio.run(db.create_document("active.md"))
        asyncio.run(db.create_document("archived.md"))
        asyncio.run(db.update_document_status("archived.md", "archived"))
        asyncio.run(db.create_document("deleted.md"))
        asyncio.run(db.update_document_status("deleted.md", "deleted"))

        # List all documents (no status filter)
        all_docs = db.list_documents()
        assert len(all_docs) == 3

        # List with None status (same as above)
        all_docs_none = db.list_documents(status=None)
        assert len(all_docs_none) == 3

    @pytest.mark.asyncio
    async def test_archive_does_not_move_files(self, db):
        """Test that archiving a document does NOT move the file on disk"""
        # Create a real temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            test_file_path = Path(f.name)
            f.write("# Test Document\n\nThis is a test document.")

        try:
            # Create document record
            await db.create_document(str(test_file_path), task_id=None)

            # Verify file exists before archiving
            assert test_file_path.exists(), "Test file should exist before archiving"

            # Archive the document (status change only)
            result = await db.update_document_status(str(test_file_path), "archived", notes="Archiving test")
            assert result is True

            # Verify file STILL exists at original location (NOT moved)
            assert test_file_path.exists(), "File should remain at original location after archiving"

            # Verify no "archive" directory was created
            archive_dir = test_file_path.parent / "archive"
            assert not archive_dir.exists(), "Archive directory should not be created"

            # Verify document status in database
            doc = db.get_document(str(test_file_path))
            assert doc["status"] == "archived"
            assert doc["notes"] == "Archiving test"

        finally:
            # Cleanup test file
            test_file_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_restore_does_not_move_files(self, db):
        """Test that restoring a document does NOT move the file on disk"""
        # Create a real temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            test_file_path = Path(f.name)
            f.write("# Test Document\n\nThis is a test document for restore.")

        try:
            # Create document record and archive it
            await db.create_document(str(test_file_path), task_id=None)
            await db.update_document_status(str(test_file_path), "archived")

            # Verify file exists before restoring
            assert test_file_path.exists(), "Test file should exist before restoring"

            # Restore the document (status change only)
            result = await db.update_document_status(str(test_file_path), "active", notes="Restore test")
            assert result is True

            # Verify file STILL exists at original location (NOT moved)
            assert test_file_path.exists(), "File should remain at original location after restoring"

            # Verify document status in database
            doc = db.get_document(str(test_file_path))
            assert doc["status"] == "active"
            assert doc["archived_at"] is None
            assert doc["notes"] == "Restore test"

        finally:
            # Cleanup test file
            test_file_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_files_stay_in_place_during_status_transitions(self, db):
        """Test that files never move during any status transitions"""
        # Create a real temporary file in docs/ style directory
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = Path(tmpdir) / "docs"
            docs_dir.mkdir()
            test_file = docs_dir / "test_doc.md"
            test_file.write_text("# Test\n\nContent here.")

            # Create document record
            await db.create_document(str(test_file), task_id=None)

            # Verify file exists
            assert test_file.exists(), "File should exist initially"

            # Test active -> archived transition
            await db.update_document_status(str(test_file), "archived")
            assert test_file.exists(), "File should stay in place after archiving"
            assert not (docs_dir / "archive").exists(), "Archive directory should not be created"

            # Test archived -> active transition (restore)
            await db.update_document_status(str(test_file), "active")
            assert test_file.exists(), "File should stay in place after restoring"

            # Test active -> deleted transition
            await db.update_document_status(str(test_file), "deleted")
            assert test_file.exists(), "File should stay in place even when marked deleted"

            # Verify database reflects status change but file is intact
            doc = db.get_document(str(test_file))
            assert doc["status"] == "deleted"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
