"""Regressions for Codex's audit of 56c4f83 (docs/Codex_Full_Code_Audit_20260928_56c4f83.md). Each
test is one of Codex's reproductions with the assertion turned to the correct behaviour."""

import hashlib
import io
import json
from datetime import timedelta

from docx import Document

from app.core.auth import User
from app.documents.docx_io import read_docx
from app.jobs.models import Job, JobStatus, ReadinessItem, StoredFile, utcnow
from app.proposals import decisions, rulebook, service
from app.proposals.models import ChapterDocument, ChapterSection, StoredChapterVersion
from app.runtime import get_runtime
from tests import conftest as fixtures
from tests.test_api import ADMIN, STUDENT
from tests.test_proposals import _create, plan

UID = "u_" + hashlib.sha256(b"student@example.com").hexdigest()[:20]
OWNER = User(uid=UID, email="student@example.com", is_admin=False)


def _paper(rt, *, words=None, scope=None, notes=None):
    data = fixtures.fixture_bytes("simple_essay.docx")
    model = read_docx(data)
    job = Job(
        id="job_auditpaper", status=JobStatus.DRAFT, owner_uid=UID, owner_email="student@example.com",
        expires_at=utcnow() + timedelta(days=30), scope_words=scope, fix_notes=notes or {},
    )
    path = f"{job.storage_prefix()}/input/source.docx"
    rt.files.put(path, data, "application/octet-stream")
    job.source = StoredFile(
        name="essay.docx", format="DOCX", size_bytes=len(data), word_count=words or model.word_count, page_estimate=1, heading_count=1,
        path=path, sha256=hashlib.sha256(data).hexdigest(),
    )
    rt.store.create(job)
    return job, model


def _project(client, number=1, *, unreviewed=False):
    """A project with an approved plan and a written, approved chapter (no AI)."""
    rt = get_runtime()
    pid = _create(client)["id"]
    p = rt.store.get_project(pid)
    approved = plan()
    sections = [
        ChapterSection(
            key=s.key, number=s.number, heading=s.heading, paragraphs=[f"The proposed study will examine caregiver access in {s.heading}."],
            depends=decisions.stamp(number, s.key, approved),
        )
        for s in rulebook.sections(p.rulebook, number, p.inputs.level, approved)
    ]
    chapter = ChapterDocument(
        number=number, title=rulebook.chapter_spec(p.rulebook, number)["title"], plan_version=1, sections=sections, cited=[], words=200,
        warnings=["Background was not reviewed."] if unreviewed else [],
        readiness=[
            ReadinessItem(
                id=f"C{number}-REVIEWED", question="Every section reviewed", basis="CODE", status="NEEDS_REVIEW" if unreviewed else "PASS",
                note="Background unreviewed" if unreviewed else "", chapter=number,
            )
        ],
    )
    path = f"{p.storage_prefix()}/chapters/{number}/seed.json"
    rt.files.put(path, chapter.model_dump_json(by_alias=True).encode(), "application/json")

    def set_up(q):
        q.plan, q.plan_status, q.plan_version = approved, "APPROVED", 1
        state = q.chapter(number)
        state.current, state.approved = 1, True
        state.versions = [StoredChapterVersion(version=1, job_id="job_seed", words=200, plan_version=1, path=path)]
        return q

    rt.store.update_project(pid, set_up)
    return pid, chapter


# --- H01 ------------------------------------------------------------------------------------------


def test_h01_admin_and_expired_views_never_carry_fix_notes(client):
    from app.jobs.service import without_paper_text

    rt = get_runtime()
    job, _ = _paper(rt, notes={"b00001": ["PRIVATE author sentence and confidential fix instruction"]})
    response = client.get(f"/api/admin/jobs/{job.id}", headers=ADMIN)
    assert response.status_code == 200 and "PRIVATE" not in json.dumps(response.json())
    assert without_paper_text(job).fix_notes == {}


def test_h01_every_job_field_is_classified_for_support_views():
    """A new Job field must be declared paper-bearing (emptied for support and expiry) or support
    metadata; this fails until it is."""
    from app.jobs.service import PAPER_FIELDS, SUPPORT_FIELDS

    assert not PAPER_FIELDS & SUPPORT_FIELDS
    assert set(Job.model_fields) == PAPER_FIELDS | SUPPORT_FIELDS


# --- H02 ------------------------------------------------------------------------------------------


def test_h02_deleting_the_account_erases_the_credit_history(client):
    rt = get_runtime()
    assert rt.store.ledger(UID, None, 10)  # the test credits
    rt.settings.credits_enabled = False
    assert client.delete("/api/me", headers=STUDENT).status_code == 204
    assert rt.store.get_wallet(UID).closing  # the tombstone still refuses late requests
    assert rt.store.ledger(UID, None, 10) == []
    rt.store.update_wallet(UID, "", lambda w: w)  # touching the tombstone adds nothing back
    assert rt.store.ledger(UID, None, 10) == []


# --- H03 ------------------------------------------------------------------------------------------


def test_h03_a_guide_arriving_after_deletion_leaves_nothing_behind(client, monkeypatch):
    rt = get_runtime()
    pid = _create(client)["id"]
    prefix = rt.store.get_project(pid).storage_prefix()
    original_put = rt.files.put
    paths = []

    def racing_put(path, data, content_type):
        if path.startswith(prefix + "/guide/"):
            service.delete(rt, OWNER, pid)
            paths.append(path)
        return original_put(path, data, content_type)

    monkeypatch.setattr(rt.files, "put", racing_put)
    doc = Document()
    doc.add_paragraph("PRIVATE institution research guide " * 120)
    out = io.BytesIO()
    doc.save(out)
    response = client.post(f"/api/projects/{pid}/guide", headers=STUDENT, files={"file": ("guide.docx", out.getvalue(), "application/octet-stream")})
    assert response.status_code == 404 and rt.store.get_project(pid) is None
    assert paths and not rt.files.exists(paths[0])


# --- H04 ------------------------------------------------------------------------------------------


def _legacy(client):
    rt = get_runtime()
    pid, chapter = _project(client)
    legacy_path = f"users/{UID}/projects/{pid}/chapters/1/legacy.json"
    rt.files.put(legacy_path, chapter.model_dump_json(by_alias=True).encode(), "application/json")

    def legacy(p):
        p.chapter(1).versions[0].path = legacy_path
        return p

    rt.store.update_project(pid, legacy)
    return rt, pid, legacy_path


def test_h04_deleting_a_project_removes_files_under_the_old_prefix(client):
    rt, pid, legacy_path = _legacy(client)
    assert client.get(f"/api/projects/{pid}/chapters/1", headers=STUDENT).status_code == 200
    assert client.delete(f"/api/projects/{pid}", headers=STUDENT).status_code == 204
    assert not rt.files.exists(legacy_path)


def test_h04_old_projects_are_migrated_out_of_the_fixed_age_prefix(client):
    from app.jobs import service as jobs

    rt, pid, legacy_path = _legacy(client)
    assert jobs.migrate_legacy_project_files(rt) == 1
    project = rt.store.get_project(pid)
    moved = project.chapter(1).versions[0].path
    assert moved.startswith(project.storage_prefix()) and rt.files.exists(moved) and not rt.files.exists(legacy_path)
    assert client.get(f"/api/projects/{pid}/chapters/1", headers=STUDENT).status_code == 200
    assert jobs.migrate_legacy_project_files(rt) == 0  # safe to repeat


def test_h04_a_step_priced_before_the_migration_still_reads_its_files(client):
    from app.jobs import service as jobs
    from app.proposals.pipeline import load_library

    rt, pid, legacy_path = _legacy(client)
    evidence_path = f"users/{UID}/projects/{pid}/evidence/job_old.json"
    rt.files.put(evidence_path, b"[]", "application/json")
    rt.store.update_project(pid, lambda p: p.model_copy(update={"evidence_files": [evidence_path]}))
    jobs.migrate_legacy_project_files(rt)
    assert not rt.files.exists(evidence_path)
    assert load_library(rt.files, [evidence_path]) == {}  # read from the moved copy, not a crash
