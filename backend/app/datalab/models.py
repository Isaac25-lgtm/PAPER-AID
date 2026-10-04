"""Data Lab records. A project lives in its own `datalab` collection (metadata only); the dataset,
its versions (Parquet), the profile and every result (JSON) and chart (PNG) live in file storage
under the project's prefix, so no row of data is ever written to the database."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.jobs.models import Camel, utcnow

Kind = Literal["NUMERIC", "CATEGORICAL", "BINARY", "DATE", "TEXT", "IDENTIFIER"]
# PERSONAL: a likely direct identifier (name, phone, email, ID number, exact location); excluded by
# default. RECORD_ID: a unique code per row. SURVEY_DESIGN: may be a sampling weight, cluster or
# stratum (decision 2026-10-03: asked, never assumed). LOCATION: coordinates. FEW_VALUES: a number
# with few distinct values, which may be codes for categories. LONG_NUMBER: whole numbers too long to
# store exactly as numbers (kept as text, never rounded).
# DECIMAL_COMMA: numbers written with a decimal comma (1,5) or dots between thousands (1.234,5): kept as
# written until the researcher confirms reading them as numbers (owner decision 2026-10-04).
Flag = Literal["PERSONAL", "RECORD_ID", "SURVEY_DESIGN", "LOCATION", "FEW_VALUES", "LEADING_ZEROS", "MIXED", "LONG_NUMBER", "DECIMAL_COMMA"]


class Level(Camel):
    value: str
    count: int


class Variable(Camel):
    name: str  # the column name as uploaded
    label: str = ""  # the researcher's own label, used in tables and text
    kind: Kind
    stored: Literal["number", "text", "date"]  # how the version stores it
    valid: int
    missing: int
    distinct: int
    levels: list[Level] = []  # categories and binary variables: up to 50, most common first
    summary: dict[str, float] = {}  # numbers: min, q1, median, mean, q3, max, sd
    flags: list[Flag] = []
    excluded: bool = False  # left out of analysis (personal identifiers and coordinates by default)
    note: str = ""

    def title(self) -> str:
        return self.label or self.name


class CleaningStep(Camel):
    """One change to the data, proposed and confirmed (or automatic under an explicit rule), with
    what it did. The original upload is never changed: each applied step makes a new version."""

    id: str
    kind: Literal["TRIM", "MERGE_LEVELS", "SET_MISSING", "OUT_OF_RANGE", "DUPLICATES", "DECIMAL_COMMA"]
    column: str = ""  # "" for whole-row steps
    params: dict[str, str | float | list[str] | dict[str, str]] = {}
    params_path: str = ""  # long parameters (a merge of many spellings) live in file storage, not the record
    description: str  # plain language: what it will do, or did
    question: str = ""  # the confirmation shown to the researcher
    affected: int = 0  # cells or rows it changes
    automatic: bool = False
    status: Literal["PROPOSED", "APPLIED", "DECLINED"] = "PROPOSED"
    version: int | None = None  # the version it produced
    decided_at: datetime | None = None


class DatasetVersion(Camel):
    version: int
    path: str  # Parquet in file storage
    rows: int
    columns: int
    sha256: str
    created_at: datetime = Field(default_factory=utcnow)
    note: str = ""
    profile: str = ""  # its variables' profile (JSON in file storage)


class Cell(Camel):
    text: str  # as shown (a hidden cell shows the neutral mark "–")
    value: float | None = None  # the number behind it, when there is one (None when suppressed)
    count: bool = False  # a count of records: subject to disclosure control
    suppressed: bool = False


class ResultTable(Camel):
    title: str
    columns: list[str]
    rows: list[list[Cell]]
    notes: list[str] = []


class Estimate(Camel):
    """A headline number: an effect size, a difference or a coefficient, with its interval."""

    name: str
    value: float
    low: float | None = None
    high: float | None = None
    level: float = 0.95
    note: str = ""


class CalculationRecord(Camel):
    """How a result was calculated (decision 2026-10-03): hidden by default, always available, and
    in the report's methods appendix."""

    question: str
    method: str
    why: str
    dataset_version: int
    cleaning: list[str] = []  # the applied steps, in plain language
    rows_used: int
    rows_available: int
    left_out: list[str] = []  # why the other rows were not used
    coding: list[str] = []  # how each variable was coded (reference category, levels compared)
    missing: str = "Records missing any variable in this analysis were left out (complete cases)."
    alpha: float = 0.05
    assumptions: list[str] = []
    software: list[str] = []
    calculated_at: datetime = Field(default_factory=utcnow)
    filters: str = ""  # the records it was limited to, in words ("" for all)


class Filter(Camel):
    """A condition on one variable (app.datalab.engine.filters): its categories, or a range."""

    variable: str
    op: Literal["IN", "NOT_IN", "BETWEEN"]
    values: list[str] = Field(default=[], max_length=50)  # IN / NOT_IN: the categories, as the profile lists them
    low: str = Field(default="", max_length=40)  # BETWEEN: a number, or a date (YYYY-MM-DD); "" for no lower bound
    high: str = Field(default="", max_length=40)  # a date-only upper bound includes that whole day


class AnalysisSpec(Camel):
    kind: Literal["DESCRIBE", "CROSSTAB", "COMPARE_TWO", "CORRELATE", "MAP"]
    variables: list[str] = Field(min_length=1, max_length=2)
    method: Literal["", "MEANS", "DISTRIBUTIONS", "PEARSON", "SPEARMAN", "COUNT", "MEAN", "RATE"] = ""
    groups: list[str] = Field(default=[], max_length=2)  # COMPARE_TWO: the two groups compared, when the variable has more
    question: str = Field(default="", max_length=300)
    objective: int | None = Field(default=None, ge=1, le=12)  # Chapter Four: the specific objective it answers (1-based)
    filters: list[Filter] = Field(default=[], max_length=5)  # only the records matching every one (owner decision 2026-10-04)
    region: Literal["", "Central", "Eastern", "Northern", "Western"] = ""  # MAP: one region, or the whole country
    subregion: str = Field(default="", max_length=40)  # MAP: one of the 15 sub-regions
    aliases: dict[str, str] = Field(default={}, max_length=300)  # MAP: place names the researcher matched themselves
    # MAP (owner decision 2026-10-04): the areas drawn; a subcounty is named with its district (names repeat)
    level: Literal["DISTRICT", "SUBCOUNTY", "SUBREGION", "REGION"] = "DISTRICT"
    subcounty: str = Field(default="", max_length=120)  # SUBCOUNTY: the column holding subcounty names
    # RECORDS: each row is one record (counted, or a number averaged); TOTALS: each row already holds an
    # area's total (a count column, and for a rate the population column it is divided by)
    data_form: Literal["RECORDS", "TOTALS"] = "RECORDS"
    total: str = Field(default="", max_length=120)
    denominator: str = Field(default="", max_length=120)

    def names(self) -> list[str]:
        """Every variable it reads: its own, the map's columns and the filters'."""
        extra = [self.subcounty, self.total, self.denominator, *(f.variable for f in self.filters)]
        return list(dict.fromkeys([*self.variables, *(n for n in extra if n)]))


class AnalysisResult(Camel):
    id: str
    spec: AnalysisSpec
    status: Literal["VALID", "VALID_WITH_WARNINGS", "NOT_ESTIMABLE"]
    title: str
    tables: list[ResultTable] = []
    statistics: dict[str, float] = {}  # every number the text may use, by name
    estimates: list[Estimate] = []
    sentences: list[str] = []  # the plain-language explanation, written by code from the numbers
    warnings: list[str] = []
    record: CalculationRecord
    chart: str = ""  # path of the PNG chart, when one helps
    matches: dict[str, str] = {}  # MAP: suggested district for a name that did not match (applied only once confirmed)
    unmatched: list[str] = []  # MAP: names that could not be placed on the map
    created_at: datetime = Field(default_factory=utcnow)


class SourceFile(Camel):
    name: str
    path: str  # the upload as PaperAid received it, never changed (the researcher's original stays on their device)
    removed: list[str] = []  # columns the researcher removed in their browser before uploading, by kind ("2 columns: phone numbers")
    sha256: str
    bytes: int
    sheet: str | None = None
    sheets: list[str] = []


class VariableSetting(Camel):
    """What the researcher set for a variable: kept with the project, applied over the profile."""

    label: str = Field(default="", max_length=120)
    kind: Kind | None = None
    excluded: bool | None = None
    survey: Literal["", "DESIGN", "NOT_DESIGN"] = ""  # their answer for a column flagged SURVEY_DESIGN
    # A column left out because it may identify people or places (names, phone numbers, exact
    # coordinates) included again: a recorded decision, named in the report's methods (Codex audit 3).
    released_at: datetime | None = None
    released_by: str = ""


class AnalysisRef(Camel):
    id: str
    kind: str
    title: str
    status: str
    version: int
    path: str  # the result's JSON in file storage
    objective: int | None = None  # Chapter Four: the specific objective it answers
    objective_sha: str = ""  # that objective's wording when it was linked: a changed objective is checked again
    variables: list[str] = []
    spec_sha: str = ""  # the analysis as asked (its objective excepted)
    # Everything the result depended on (the data, the variables' settings, the significance level,
    # the disclosure threshold, the survey answers, the rules): a different fingerprint now means the
    # result is out of date (Codex audit, finding 4).
    fingerprint: str = ""
    rows: str = ""  # the rows it used, as a compressed bitmap in file storage ("" for analyses from before 2026-10-05)
    created_at: datetime = Field(default_factory=utcnow)


class ReportVersion(Camel):
    version: int
    path: str  # the report document's JSON (sections, with numbers filled in)
    docx: str
    job_id: str
    analyses: list[str]  # the analyses it reports (a qualitative analysis: the documents it read)
    kind: Literal["REPORT", "CHAPTER_FOUR", "THEMES"] = "REPORT"
    workbook: str = ""  # a qualitative analysis: its codebook (Excel)
    created_at: datetime = Field(default_factory=utcnow)


class QualDocument(Camel):
    """A transcript or set of open answers (qualitative Data Lab, owner decision 2026-10-04), kept as text
    after the names the researcher listed, and any email address, phone or ID number, were replaced."""

    id: str
    label: str = Field(max_length=80)  # how the report names it: "Interview 3", "Focus group, Gulu"
    name: str  # the file it came from ("" when pasted)
    path: str  # the cleaned text in file storage
    sha256: str
    words: int
    replaced: int = 0  # names and identifiers replaced before it was stored
    created_at: datetime = Field(default_factory=utcnow)


class DataOp(Camel):
    """One piece of data work run in the worker (Codex audit, finding 13): reading a file, applying or
    undoing a change, an analysis, the cleaned-data file. A project runs one at a time; its result is
    kept only if the data it used is still the project's data."""

    id: str  # dop_<project id>_<token>: the worker finds the project from it
    kind: Literal["LOAD", "SHEET", "DECIDE", "UNDO", "ANALYSE", "CLEANED"]
    params: dict = {}
    status: Literal["QUEUED", "RUNNING", "DONE", "FAILED"] = "QUEUED"
    error: str = ""
    code: str = ""
    result: str = ""  # an analysis id, or a file path
    created_at: datetime = Field(default_factory=utcnow)
    lease_until: datetime | None = None
    attempt: str = ""  # the claim that owns it: only that worker may finish it (Codex audit 2026-10-04, finding 6)


class Export(Camel):
    path: str
    fingerprint: str
    rows: int
    created_at: datetime = Field(default_factory=utcnow)


class DataProject(Camel):
    """A Data Lab project: metadata only. Rows, levels, results and reports live in file storage.
    Quantitative (a dataset of numbers and categories) or qualitative (transcripts and open answers)."""

    id: str
    kind: Literal["QUANT", "QUAL"] = "QUANT"
    documents: list[QualDocument] = []  # qualitative: the transcripts
    owner_uid: str
    owner_email: str
    title: str = Field(default="", max_length=200)
    purpose: str = Field(default="", max_length=1500)  # what the researcher wants to find out, for the report
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    deleting: bool = False
    source: SourceFile | None = None
    versions: list[DatasetVersion] = []
    current: int = 0  # the version analyses use
    profile_path: str = ""  # the current version's variables (JSON in storage)
    settings: dict[str, VariableSetting] = {}
    steps: list[CleaningStep] = []
    analyses: list[AnalysisRef] = []
    alpha: float = 0.05
    threshold: int = 5  # disclosure: counts below this are not shown (decision 2026-10-03); can be raised, never lowered
    reports: list[ReportVersion] = []
    report_current: int = 0
    active_job: str | None = None
    jobs: list[str] = []
    # Chapter Four of a research proposal (owner decision 2026-10-03): the proposal it belongs to and its
    # approved specific objectives, copied when the data was linked; its analyses are written up by objective.
    proposal_id: str = ""
    objectives: list[str] = []
    op: DataOp | None = None  # the data work running in the worker, or the last one
    country: str = ""  # where the data is from (ISO 3166 alpha-3, or OTHER): data protection depends on it
    consent: dict = {}  # the researcher's confirmation at the last upload: wording version, terms version, when
    cleaned: Export | None = None  # the cleaned-data file last made

    def storage_prefix(self) -> str:
        # Outside users/ like works: kept while the project is renewed, removed by the app's own cleanup.
        return f"datalab/{self.owner_uid}/{self.id}"
