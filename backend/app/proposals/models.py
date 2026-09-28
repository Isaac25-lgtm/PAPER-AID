"""Proposal project contracts (Proposal V1, owner decision 2026-09-28). A proposal is a persistent
project, not a one-off job: the student's inputs, the approved plan, each chapter's versions and
the evidence library live here, while every paid AI step (the plan, each chapter) runs as an
ordinary job linked to the project. Field names serialise to camelCase like the job contracts.

Firestore keeps only this record (metadata and short text). Chapter text and evidence live in
storage, one immutable file per job, so two jobs finishing together can never overwrite each
other: the record only gains the new file's path, inside a transaction."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.jobs.models import Camel, ReadinessItem, utcnow

Level = Literal["BACHELORS", "PGD", "MASTERS", "PHD"]
StudyType = Literal["QUANTITATIVE", "QUALITATIVE", "MIXED", "SECONDARY", "NON_EMPIRICAL"]
QuestionsKind = Literal["QUESTIONS", "HYPOTHESES", "PROPOSITIONS"]
Support = Literal["SUPPORTED", "PARTLY_SUPPORTED", "CONTRADICTED", "NOT_FOUND"]


def _clean(value: str) -> str:
    return " ".join(value.split())


class ProposalInputs(Camel):
    """What the student tells PaperAid about the study. Sent to the AI models, so it never holds the
    student's name or registration number (those are on `TitlePage`)."""

    topic: str = Field(min_length=10, max_length=300)
    level: Level
    programme: str = Field(default="", max_length=150)
    faculty: str = Field(default="", max_length=150)
    study_area: str = Field(default="", max_length=200)
    population: str = Field(default="", max_length=200)
    study_type: StudyType | None = None  # None: the student is not sure yet; the plan proposes one
    notes: str = Field(default="", max_length=4000)  # concept summary, supervisor guidance, anything already decided
    # The student's own figures, entered as such (Codex audit 2026-09-28 #13): the only accepted
    # source of a population size or a stated sample. A number elsewhere (a year, an age) never is.
    population_size: int | None = Field(default=None, ge=1, le=100_000_000)
    population_source: str = Field(default="", max_length=300)
    expected_participants: int | None = Field(default=None, ge=1, le=1_000_000)

    @field_validator("topic", "programme", "faculty", "study_area", "population")
    @classmethod
    def _one_line(cls, value: str) -> str:
        return _clean(value)


class TitlePage(Camel):
    """Only printed on the title page. Never sent to an AI model or a search."""

    student_name: str = Field(default="", max_length=120)
    reg_number: str = Field(default="", max_length=60)
    supervisor: str = Field(default="", max_length=160)
    submission_date: str = Field(default="", max_length=40)  # as it should be printed, e.g. "October 2026"


class Variables(Camel):
    independent: list[str] = []
    dependent: list[str] = []
    intervening: list[str] = []


class AlignmentRow(Camel):
    """One row of the objective-to-method matrix: how an objective will be answered."""

    objective: int  # 1-based position in `specific_objectives`
    data: str = Field(max_length=800)  # the data or information the objective needs
    collection: str = Field(max_length=800)  # how it will be collected (method and instrument)
    analysis: str = Field(max_length=1000)  # how it will be analysed


SampleMethod = Literal["YAMANE", "COCHRAN", "KREJCIE_MORGAN", "CENSUS", "SATURATION", "AUTHOR_STATED", "NOT_APPLICABLE"]


class SampleSize(Camel):
    """How the sample size is reached. Every figure here is the student's: PaperAid calculates the
    size from them (app.proposals.sampling) and never supplies a population size itself."""

    method: SampleMethod = "NOT_APPLICABLE"
    population: int | None = Field(default=None, ge=1, le=100_000_000)  # the accessible population N
    population_source: str = Field(default="", max_length=300)  # where the student's figure comes from
    margin: float = Field(default=0.05, gt=0, lt=0.5)
    confidence: Literal[90, 95, 99] = 95
    proportion: float = Field(default=0.5, gt=0, lt=1)
    stated: int | None = Field(default=None, ge=1, le=1_000_000)  # the student's own number (qualitative, or a stated size)
    rationale: str = Field(default="", max_length=600)


class ProposalPlan(Camel):
    """The research logic every chapter is written from. Drafted by the AI, then edited and
    approved by the student; chapters are only written from an approved plan. Each decision has a
    stable id (app.proposals.decisions), so a change can be traced to the sections it affects."""

    title: str = Field(max_length=300)
    problem: str = Field(max_length=2000)  # the core of the problem statement
    purpose: str = Field(max_length=600)  # the general objective
    specific_objectives: list[str]
    questions_kind: QuestionsKind = "QUESTIONS"
    research_questions: list[str]  # or hypotheses / propositions, one per objective
    study_type: StudyType
    design: str = Field(max_length=600)
    study_area: str = Field(default="", max_length=400)
    population: str = Field(default="", max_length=400)
    sampling: str = Field(default="", max_length=800)  # the sampling technique and procedure
    sample_size: SampleSize = Field(default_factory=SampleSize)
    inclusion: str = Field(default="", max_length=600)  # inclusion and exclusion criteria
    variables: Variables = Field(default_factory=Variables)
    alignment: list[AlignmentRow] = []
    theory: str = Field(default="", max_length=800)  # the theory or framework and why it fits
    scope: str = Field(max_length=800)  # geographical, time and content scope
    timeline_months: int = Field(default=6, ge=1, le=48)  # the work plan's length, the student's choice
    gaps: list[str] = []  # where the evidence found so far is thin
    questions_for_student: list[str] = []  # what the student should confirm or decide


class EvidenceSource(Camel):
    """Where a piece of evidence was read. Bibliographic details come from Crossref or OpenAlex
    when the source has a DOI; otherwise from the page, and the reference says so."""

    url: str
    title: str
    authors: list[str] = []  # "Surname, G." as APA lists them
    organisation: str = ""  # a group author (WHO, Ministry of Health) when there are no personal authors
    year: str = ""  # "" prints as n.d.
    container: str = ""  # journal or website
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    kind: Literal["ARTICLE", "REPORT", "WEB"] = "WEB"
    metadata: Literal["CROSSREF", "OPENALEX", "PAGE"] = "PAGE"


class EvidenceItem(Camel):
    """One finding, quoted from one source. It may be cited in a chapter only if `usable`: PaperAid
    found the quoted passage itself and the second model agreed it supports the statement."""

    id: str  # "E" + a stable hash; the token the writer cites (⟦E1a2b3c⟧)
    chapter: int  # 0 = gathered for the plan
    need: str  # the research need it answers
    statement: str  # what the source shows, in one sentence
    passage: str  # the source's own words
    scope: str = ""  # population, place and period the source covers
    access: Literal["FULL_TEXT", "ABSTRACT", "SNIPPET"] = "SNIPPET"
    verified: bool = False  # PaperAid found the passage on the page or in the abstract
    support: Support = "NOT_FOUND"  # the second model's check of passage against statement
    source: EvidenceSource
    retrieved_on: str

    @property
    def usable(self) -> bool:
        return self.verified and self.support in ("SUPPORTED", "PARTLY_SUPPORTED")


class ChapterVersion(Camel):
    version: int
    job_id: str
    created_at: datetime = Field(default_factory=utcnow)
    words: int
    plan_version: int  # the approved plan it was written from
    passed: int = 0  # readiness items that passed
    total: int = 0
    note: str = ""  # the student's instruction for this version, if any


class StoredChapterVersion(ChapterVersion):
    path: str  # the version file in storage (never shown to browsers)


class ChapterState(Camel):
    number: int
    current: int = 0  # the version shown and exported (0: none yet)
    approved: bool = False  # the student approved the current version
    versions: list[ChapterVersion] = []
    needs_review: list[str] = []  # headings of current sections whose decisions changed (computed for the view)


class StoredChapterState(ChapterState):
    versions: list[StoredChapterVersion] = []  # type: ignore[assignment]


PlanStatus = Literal["NONE", "DRAFT", "APPROVED"]
CitationStyle = Literal["APA6", "APA7"]


class ProjectView(Camel):
    """What the owner's browser sees."""

    id: str
    kind: Literal["PROPOSAL"] = "PROPOSAL"
    rulebook: str
    citation: CitationStyle = "APA6"
    inputs: ProposalInputs
    title_page: TitlePage = Field(default_factory=TitlePage)
    plan: ProposalPlan | None = None
    plan_status: PlanStatus = "NONE"
    plan_version: int = 0  # rises with every change to the plan; edits must name the version they started from
    plan_problems: list[str] = []  # what must be fixed before the plan can be approved (computed for the view)
    candidate_plan: ProposalPlan | None = None  # a plan PaperAid produced while the student was editing theirs
    chapters: list[ChapterState]
    evidence_count: int = 0
    active_job: str | None = None  # the step running now, if any
    jobs: list[str] = []  # every job run for this project, newest last
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime  # 30 days after the student's last action (owner decision 2026-09-28)


class Project(ProjectView):
    """The full server record."""

    owner_uid: str
    owner_email: str
    chapters: list[StoredChapterState]  # type: ignore[assignment]
    evidence_files: list[str] = []  # one file per job that gathered evidence
    published: list[str] = []  # jobs whose results were published here (a retried publish adds nothing)
    deleting: bool = False  # claimed for deletion (by the student, account deletion or expiry): nothing new may start

    def view(self) -> ProjectView:
        return ProjectView.model_validate(self.model_dump())

    def storage_prefix(self) -> str:
        # Outside users/: the bucket's fixed-age backstop covers job files only; project files live
        # while the project is renewed and are removed by the app's own cleanup (Codex audit #3).
        return f"projects/{self.owner_uid}/{self.id}"

    def chapter(self, number: int) -> StoredChapterState:
        return next(c for c in self.chapters if c.number == number)


class ChapterSection(Camel):
    key: str
    number: str
    heading: str
    paragraphs: list[str]  # citations stay as evidence tokens; they are rendered in the project's style when shown
    table: list[list[str]] | None = None  # first row is the header
    table_caption: str = ""
    depends: dict[str, str] = {}  # decision id → the hash it was written from (app.proposals.decisions)


class StepInput(Camel):
    """What a proposal step runs on, frozen when it is priced (Codex review: a job publishes against
    its input version). Stored with the job; its hash binds the quote."""

    project_id: str
    step: Literal["PLAN", "CHAPTER"]
    chapter: int  # 0 for the plan
    note: str = ""  # the student's instruction for this run
    rulebook: str
    inputs: ProposalInputs
    plan: ProposalPlan | None = None  # the approved plan (chapters only)
    plan_version: int
    evidence_files: list[str] = []
    chapters: dict[int, str] = {}  # the other chapters' current version files, for consistency checks
    private: list[str] = []  # title-page words that must never reach a search (never sent to a model)


class ChapterDocument(Camel):
    """One version of a chapter, as stored."""

    number: int
    title: str
    plan_version: int
    sections: list[ChapterSection]
    cited: list[str]  # evidence ids cited, in order of first use
    readiness: list[ReadinessItem] = []
    warnings: list[str] = []
    words: int
