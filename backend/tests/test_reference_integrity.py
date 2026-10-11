"""References (owner, 2026-10-11: "referencing is a big deal"). Each test is a defect found in the documents of the
trials of 9 and 10 October by the academic audit of 10 October; the record or page is as it was registered."""

import pytest

from app.analysis import fetch
from app.analysis.metadata import clean_authors, clean_text, clean_title
from app.proposals import evidence, pipeline
from app.proposals.models import EvidenceItem, EvidenceSource

PAGE_META = fetch.page_meta  # the real one: a fixture below stands in for it


def test_a_place_of_work_registered_as_an_author_is_not_printed_as_one():
    registered = ["Faculty of Business and Management, Universiti Teknologi MARA, Malaysia", "Borhan, N. A.", "Muda, R.",
                  "Faculty of Business and Management, Universiti Teknologi MARA, Malaysia", "Mohamad, S.",
                  "Faculty of Business and Management, Universiti Teknologi MARA, Malaysia"]
    assert clean_authors(registered) == ["Borhan, N. A.", "Muda, R.", "Mohamad, S."]
    kyambogo = ["Department of Educational Planning and Management, School of Education, Kyambogo University", "MUGIZI, W.", "RWOTHUMIO, J."]
    assert clean_authors(kyambogo) == ["Mugizi, W.", "Rwothumio, J."]


def test_an_organisation_that_is_the_only_author_stays_the_author():
    assert clean_authors(["Uganda Bureau of Statistics"]) == ["Uganda Bureau of Statistics"]
    assert clean_authors(["Ministry of Health"]) == ["Ministry of Health"]
    assert clean_authors(["Makerere University School of Public Health"]) == ["Makerere University School of Public Health"]  # nobody else is named: it wrote it
    assert clean_authors(["Okello, J.", "RTS,S Clinical Trials Partnership"]) == ["Okello, J.", "RTS,S Clinical Trials Partnership"]  # a group author beside a person


def test_degrees_capitals_and_repeats_are_not_part_of_a_name():
    assert clean_authors(["MAKHANDIA, C. S.", "MIROGA (PhD), D. J.", "OTINGA (PhD), D. C. H. N."]) == ["Makhandia, C. S.", "Miroga, D. J.", "Otinga, D. C. H. N."]
    assert clean_authors(["Dr. Okello, J.", "", "  "]) == ["Okello, J."]
    assert clean_authors(["WHO"]) == ["WHO"] and clean_authors(["Ng, K."]) == ["Ng, K."]  # an acronym and a short surname are left alone


def test_markup_and_entities_never_reach_a_reference():
    assert clean_text("Cogent Economics &amp; Finance") == "Cogent Economics & Finance"
    assert clean_title("<scp>ICT</scp> for financial access: Mobile money in Uganda") == "ICT for financial access: Mobile money in Uganda"
    assert clean_title("Adapt or Perish: Remote Working Challenges&lt;b&gt;&lt;/b&gt;") == "Adapt or Perish: Remote Working Challenges"
    assert clean_text("PM&amp;amp;R") == "PM&R"  # escaped twice
    assert clean_title("Prevalence where p < 0.05 and n > 30") == "Prevalence where p < 0.05 and n > 30"  # a comparison is not markup
    shouted = clean_title("MOBILE MONEY SERVICES AND FINANCIAL GROWTH OF SMALL AND MEDIUM ENTERPRISES IN KAKAMEGA TOWN, KENYA")
    assert shouted == "Mobile Money Services and Financial Growth of Small and Medium Enterprises in Kakamega Town, Kenya"


def test_a_registered_record_is_cleaned_when_it_is_fetched():
    record = fetch._crossref_record({
        "DOI": "10.1111/RODE.12327", "title": ["<scp>ICT</scp> for financial access"], "container-title": ["Review of Development Economics &amp; Policy"],
        "author": [{"name": "Faculty of Economics, Example University, Japan"}, {"family": "MUNYEGERA (PhD)", "given": "Ggombe Kasim"}, {"family": "Matsumoto", "given": "Tomoya"}],
        "issued": {"date-parts": [[2017]]}})
    assert record["title"] == "ICT for financial access" and record["container"] == "Review of Development Economics & Policy"
    assert record["authors"] == "Munyegera, G. K.; Matsumoto, T."


def _source(**details) -> EvidenceSource:
    return EvidenceSource(**{"url": "https://example.org/a", "title": "A study of uptake", "year": "2021", **details})


def test_evidence_saved_before_is_printed_clean_too():
    saved = _source(title="<scp>ICT</scp> for access", container="Economics &amp; Finance", kind="ARTICLE", doi="10.1/x",
                    authors=["Faculty of Business, Universiti Teknologi MARA, Malaysia", "BORHAN (PhD), N. A.", "Muda, R."])
    assert evidence.reference(saved) == "Borhan, N. A., & Muda, R. (2021). ICT for access. Economics & Finance. https://doi.org/10.1/x"
    assert evidence.author_label(saved) == "Borhan & Muda"
    assert evidence._harvard(saved).startswith("Borhan, N. A. and Muda, R. (2021) ICT for access. Economics & Finance.")


def _library(*sources: EvidenceSource) -> dict[str, EvidenceItem]:
    out = {}
    for n, source in enumerate(sources, start=1):
        item_id = f"E{n:06x}"
        out[item_id] = EvidenceItem(id=item_id, chapter=1, need="n", statement="s", passage="p", scope="", access="ABSTRACT", verified=True, support="SUPPORTED",
                                    source=source, retrieved_on="2026-10-11")
    return out


def test_a_comma_between_two_citations_never_prints_the_same_one_twice():
    """ "(Opok et al., 2026), (Opok et al., 2026)" and "(Pearson, 2022), (Juaneza et al., 2026)". """
    opok = _source(url="https://example.org/opok", title="Teacher turnover in Alebtong", year="2026", authors=["Opok, S.", "Akello, R.", "Odongo, P."], doi="10.1/opok")
    pearson = _source(url="https://example.org/pearson", title="Elasticity", year="2022", authors=["Pearson, A."])
    library = _library(opok, opok.model_copy(update={"url": "https://example.org/opok-2"}), pearson)
    citer = evidence.Citer(library, "APA7")
    assert citer.render("Findings conflict with Alebtong District ⟦E000001⟧, ⟦E000002⟧ on this point.") == "Findings conflict with Alebtong District (Opok et al., 2026) on this point."
    assert citer.render("Elasticity varies ⟦E000003⟧, ⟦E000001⟧.") == "Elasticity varies (Opok et al., 2026; Pearson, 2022)."
    assert citer.render("It holds ⟦E000003⟧ and ⟦E000001⟧; later work agrees ⟦E000003⟧.") == "It holds (Opok et al., 2026; Pearson, 2022); later work agrees (Pearson, 2022)."
    assert citer.render("⟦E000003|n⟧ argues the opposite ⟦E000001⟧.") == "Pearson (2022) argues the opposite (Opok et al., 2026)."  # a narrative citation is its own


def test_one_work_reached_by_two_addresses_is_listed_once_with_its_doi():
    with_doi = _source(url="https://doi.org/10.1/opok", title="Teacher Turnover in Alebtong", year="2026", authors=["Opok, S."], doi="10.1/opok", kind="ARTICLE")
    by_page = _source(url="https://journal.example.org/view/77", title="Teacher turnover in Alebtong.", year="2026", authors=["Opok, S."], kind="ARTICLE")
    other = _source(url="https://example.org/b", title="Another study", year="2026", authors=["Opok, S."])
    listed = evidence.reference_list([by_page, with_doi, other])
    assert len(listed) == 2 and any("https://doi.org/10.1/opok" in entry for entry in listed) and not any("journal.example.org" in entry for entry in listed)


PMC_PAGE = b"""<html><head>
<meta name="citation_title" content="Cross-sectional studies: understanding applications, methodological issues, and valuable insights">
<meta content="Figueiredo, Juliana Carvalho" name="citation_author"><meta name='citation_author' content='Cecilia Maria Patino'>
<meta name="citation_author" content="Ferreira, Juliana Carvalho">
<meta name="citation_publication_date" content="2025 Apr 2"><meta name="citation_journal_title" content="Jornal Brasileiro de Pneumologia">
<meta name="citation_volume" content="51"><meta name="citation_issue" content="1"><meta name="citation_firstpage" content="e20250047">
<meta name="citation_doi" content="doi:10.36416/1806-3756/e20250047"><meta name="description" content="not a citation tag">
</head><body>Text</body></html>"""


def test_a_page_s_own_declaration_names_the_article_it_presents(monkeypatch):
    monkeypatch.setattr(fetch, "_get", lambda url: (PMC_PAGE, "text/html; charset=utf-8"))
    declared = fetch.page_meta("https://pmc.ncbi.nlm.nih.gov/articles/PMC12097739/")
    assert declared == {"title": "Cross-sectional studies: understanding applications, methodological issues, and valuable insights",
                        "authors": "Figueiredo, J. C.; Patino, C. M.; Ferreira, J. C.", "year": "2025", "container": "Jornal Brasileiro de Pneumologia",
                        "volume": "51", "issue": "1", "pages": "e20250047", "doi": "10.36416/1806-3756/e20250047"}
    monkeypatch.setattr(fetch, "_get", lambda url: (b"<html><head><title>News</title></head></html>", "text/html"))
    assert fetch.page_meta("https://example.org/news") == {}  # a page that declares no article
    monkeypatch.setattr(fetch, "_get", lambda url: (b"%PDF-1.7", "application/pdf"))
    assert fetch.page_meta("https://example.org/report.pdf") == {}
    monkeypatch.setattr(fetch, "_get", lambda url: None)
    assert fetch.page_meta("https://example.org/down") == {}


class _Finding:
    def __init__(self, url, title="Cross-sectional studies: what are they good for?", publisher="National Library of Medicine (PMC)", published="2023"):
        self.url, self.title, self.publisher, self.published = url, title, publisher, published


@pytest.fixture
def offline(monkeypatch):
    """No registration answers and no page declares anything, unless a test says otherwise."""
    monkeypatch.setattr(fetch, "resolve_doi", lambda url: "")
    monkeypatch.setattr(fetch, "crossref_work", lambda doi: None)
    monkeypatch.setattr(fetch, "crossref_search", lambda text, rows=3: [])
    monkeypatch.setattr(fetch, "page_meta", lambda url: {})
    return monkeypatch


def test_an_article_on_a_hosting_site_is_cited_by_its_authors_from_the_page(offline):
    """It was printed as "National Library of Medicine (PMC). (2023). Cross-sectional studies: what are they good for?"."""
    offline.setattr(fetch, "_get", lambda url: (PMC_PAGE, "text/html"))
    offline.setattr(fetch, "page_meta", PAGE_META)
    source = pipeline._web_source(_Finding("https://pmc.ncbi.nlm.nih.gov/articles/PMC12097739/"))
    assert source.authors == ["Figueiredo, J. C.", "Patino, C. M.", "Ferreira, J. C."] and source.year == "2025" and source.organisation == ""
    assert source.title.startswith("Cross-sectional studies: understanding applications") and source.doi == "10.36416/1806-3756/e20250047"
    assert evidence.author_label(source) == "Figueiredo et al."


def test_the_registration_is_preferred_when_the_page_gives_its_doi(offline):
    offline.setattr(fetch, "page_meta", lambda url: {"title": "A registered study", "authors": "Page, A.", "year": "2024", "container": "J", "volume": "", "issue": "", "pages": "",
                                                     "doi": "10.5/registered"})
    offline.setattr(fetch, "crossref_work", lambda doi: {"doi": doi, "title": "A registered study", "authors": "Okello, J.; Akello, R.", "year": "2024", "container": "Journal of Studies",
                                                         "volume": "3", "issue": "1", "pages": "1–9", "type": "journal-article"} if doi == "10.5/registered" else None)
    source = pipeline._web_source(_Finding("https://repository.example.ac.ug/handle/1/2", title="Some other title", publisher="Example University", published="2020"))
    assert (source.authors, source.year, source.metadata, source.doi) == (["Okello, J.", "Akello, R."], "2024", "CROSSREF", "10.5/registered")


def test_an_article_on_a_hosting_site_with_no_author_to_be_found_is_left_out(offline):
    assert pipeline._web_source(_Finding("https://pmc.ncbi.nlm.nih.gov/articles/PMC1/")) is None
    assert pipeline._web_source(_Finding("https://www.researchgate.net/publication/1_x", publisher="ResearchGate")) is None
    offline.setattr(fetch, "page_meta", lambda url: {"title": "An article", "authors": "", "year": "2022", "container": "A Journal", "volume": "", "issue": "", "pages": "", "doi": ""})
    assert pipeline._web_source(_Finding("https://journal.example.org/article/9", publisher="A Journal")) is None  # the page presents an article and names nobody


def test_an_organisation_s_own_page_is_cited_by_the_organisation(offline):
    source = pipeline._web_source(_Finding("https://www.afro.who.int/countries/uganda/news/launch", title="Uganda launches malaria vaccine", publisher="World Health Organization",
                                           published="2 April 2025"))
    assert (source.organisation, source.year, source.authors, source.kind) == ("World Health Organization", "2025", [], "REPORT")
    news = pipeline._web_source(_Finding("https://ugandaradionetwork.net/story/ple-results", title="PLE results", publisher="Uganda Radio Network", published="2025"))
    assert evidence.author_label(news) == "Uganda Radio Network"


def test_a_registration_without_authors_takes_them_from_the_index_s_own_record(offline):
    """ "Sub-Saharan teachers' conditions and circumstances: a review. (2022)." was listed with no author. """
    offline.setattr(fetch, "crossref_work", lambda doi: {"doi": doi, "title": "Sub-Saharan teachers' conditions and circumstances: a review", "authors": "", "year": "2022",
                                                         "container": "Journal of Applied Learning & Teaching", "volume": "5", "issue": "", "pages": "", "type": "journal-article"})
    work = {"doi": "10.37074/jalt.2022.5.s2.5", "url": "https://doi.org/10.37074/jalt.2022.5.s2.5", "title": "Sub-Saharan teachers' conditions", "authors": "Hennessy, S.; Koomar, S.",
            "year": "2022", "container": "JALT", "type": "article"}
    assert pipeline._scholarly_source(work).authors == ["Hennessy, S.", "Koomar, S."]


# --- found in the documents of the round of 11 October 2026 (real models, the live path) ----------------------------

def test_an_author_registered_twice_with_the_names_reversed_is_one_person():
    """ "Murendo, C., Wollni, M., Conrad, M., & Meike, W." was two authors, each registered again the other way round."""
    works = fetch._openalex_works([{
        "display_name": "Mobile money and household food security in Uganda", "abstract_inverted_index": {"Mobile": [0], "money": [1]}, "publication_year": 2016,
        "authorships": [{"author": {"display_name": n}} for n in ("Conrad Murendo", "Meike Wollni", "Murendo Conrad", "Wollni Meike")],
        "primary_location": {"source": {"display_name": "RePEc: Research Papers in Economics", "type": "repository"}}, "doi": "https://doi.org/10.22004/ag.econ.229805"}])
    assert works[0]["authors"] == "Murendo, C.; Wollni, M."
    assert works[0]["container"] == ""  # a repository keeps a copy: it is not the journal
    record = fetch._crossref_record({"title": ["A pathway to financial inclusion"], "author": [
        {"family": "Adong", "given": "Annet"}, {"family": "Kancs", "given": "d'Artis"}, {"family": "Annet", "given": "Adong"}, {"family": "d'Artis", "given": "Kancs"}]})
    assert record["authors"] == "Adong, A.; Kancs, D."  # the whole list entered again the other way round; and an initial is a capital
    assert clean_authors(["Han., C. S.", "Sing., L. W.", "Okello, J."]) == ["Han, C. S.", "Sing, L. W.", "Okello, J."]  # a full stop registered inside a surname


def test_a_work_in_another_language_is_not_offered_as_a_source():
    work = {"display_name": "Price elasticity of demand", "abstract_inverted_index": {"Price": [0]}, "authorships": [{"author": {"display_name": "Тетяна Палієнко"}}]}
    assert fetch._openalex_works([{**work, "language": "uk"}]) == []
    assert len(fetch._openalex_works([{**work, "language": "en"}])) == 1 and len(fetch._openalex_works([work])) == 1  # not stated: kept


def test_a_repository_is_never_printed_as_the_journal_and_a_journal_s_name_is_tidied():
    from app.analysis.metadata import clean_container, clean_pages

    for kept_copy in ("Institutional Repositories DataBase (IRDB)", "RePEc: Research Papers in Economics", "Aberdeen University Research Archive (Aberdeen University)",
                      "The Open University of Tanzania Repository (The Open University of Tanzania)"):
        assert clean_container(kept_copy) == "", kept_copy
    assert clean_container("International journal of marketing management.") == "International journal of marketing management"
    assert clean_container("TEXILA INTERNATIONAL JOURNAL OF PUBLIC HEALTH") == "Texila International Journal of Public Health"
    assert clean_container("SCIENCE MUNDI") == "Science Mundi" and clean_container("PLOS ONE") == "PLOS ONE" and clean_container("BMJ Open") == "BMJ Open"
    assert clean_pages("105–105") == "105" and clean_pages("671–691") == "671–691" and clean_pages("e0212270") == "e0212270" and clean_pages("") == ""
    saved = _source(kind="ARTICLE", authors=["Munyegera, G. K.", "Matsumoto, T."], year="2014", title="Mobile Money, Remittances and Rural Household Welfare",
                    container="Institutional Repositories DataBase (IRDB)", volume="14", doi="10.24545/00001158")
    assert evidence.reference(saved) == "Munyegera, G. K., & Matsumoto, T. (2014). Mobile Money, Remittances and Rural Household Welfare. https://doi.org/10.24545/00001158"
    article = _source(kind="ARTICLE", authors=["Simbeye, A. J."], year="2024", title="Suboptimal uptake of the malaria vaccine: what's behind the blinds?",
                      container="Malaria Journal.", volume="23", issue="1", pages="105–105", doi="10.1186/s12936-024-04938-7")
    assert evidence.reference(article) == ("Simbeye, A. J. (2024). Suboptimal uptake of the malaria vaccine: what's behind the blinds? Malaria Journal, 23(1), 105. "
                                           "https://doi.org/10.1186/s12936-024-04938-7")
    assert evidence.reference(article, "HARVARD").startswith("Simbeye, A. J. (2024) Suboptimal uptake of the malaria vaccine: what's behind the blinds? Malaria Journal, 23(1), pp. 105.")


def test_an_organisation_a_page_names_as_its_author_is_kept_whole(monkeypatch):
    """ "(acres), C. f. R. E. S. (2026)", cited in the text as "((acres), 2026)": the Center for Rapid Evidence Synthesis (ACRES)."""
    page = (b'<html><head><meta name="citation_title" content="Strategies to improve completion of the malaria vaccine in Mukono district">'
            b'<meta name="citation_author" content="Center for Rapid Evidence Synthesis (ACRES)">'
            b'<meta name="citation_publication_date" content="2026/02/01"></head></html>')
    monkeypatch.setattr(fetch, "_get", lambda url: (page, "text/html"))
    assert PAGE_META("https://example.org/evidence/76")["authors"] == "Center for Rapid Evidence Synthesis (ACRES)"
    source = _source(authors=["Center for Rapid Evidence Synthesis (ACRES)"], year="2026")
    assert evidence.Citer(_library(source), "APA7").render("Coverage fell ⟦E000001⟧.") == "Coverage fell (Center for Rapid Evidence Synthesis (ACRES), 2026)."
    assert evidence.reference(source).startswith("Center for Rapid Evidence Synthesis (ACRES). (2026). A study of uptake.")


def test_a_site_that_is_no_source_for_academic_work_is_never_cited(offline):
    """Wikipedia, "Academic Kids Encyclopedia" and a tutoring site were in a reference list (round of 11 October)."""
    for url in ("https://en.wikipedia.org/wiki/Touchscreen", "https://academickids.com/encyclopedia/index.php/Alphanumeric_keyboard",
                "https://www.varsitytutors.com/practice/subjects/high-school-economics/lessons/market-structures", "https://www.quora.com/What-is-an-input-device",
                "https://someone.blogspot.com/2020/01/input.html", "https://brainly.in/question/1"):
        assert pipeline._web_source(_Finding(url, title="Touchscreen", publisher="Wikipedia", published="")) is None, url
    kept = pipeline._web_source(_Finding("https://www.ubos.org/statistics/", title="Statistical abstract", publisher="Uganda Bureau of Statistics", published="2024"))
    assert kept is not None and kept.organisation == "Uganda Bureau of Statistics"
    assert pipeline._web_source(_Finding("https://openstax.org/books/principles-economics-3e/pages/5-1", title="Price elasticity", publisher="OpenStax", published="2022")) is not None  # an open textbook


# --- Codex's audit of 1a3b1e7: a cleanup never changes what is true -------------------------------------------------

def test_two_papers_with_one_title_and_year_are_two_references():
    """Finding 1: "Introduction" (2024) by different authors under different DOIs was listed once."""
    first = _source(url="https://doi.org/10.1/a", doi="10.1/a", title="Introduction", year="2024", authors=["Okello, J."], kind="ARTICLE")
    second = _source(url="https://doi.org/10.1/b", doi="10.1/b", title="Introduction", year="2024", authors=["Namara, P."], kind="ARTICLE")
    assert len(evidence.reference_list([first, second])) == 2
    long_title = "Teacher motivation and learner performance in government-aided primary schools"
    registered_twice = [_source(url=f"https://doi.org/10.1/{n}", doi=f"10.1/{n}", title=long_title, year="2024", authors=["Okello, J."], kind="ARTICLE") for n in "cd"]
    assert len(evidence.reference_list(registered_twice)) == 2  # two registrations are two works, whatever their titles
    other_author = [_source(url="https://example.org/1", title=long_title, year="2024", authors=["Okello, J."]), _source(url="https://example.org/2", title=long_title, year="2024", authors=["Namara, P."])]
    assert len(evidence.reference_list(other_author)) == 2
    cyrillic = [_source(url="https://example.org/3", title="Цінова еластичність попиту як детермінанта поведінки", year="2026", authors=["Ivanova, N."]),
                _source(url="https://example.org/4", title="Трансформація життєво важливих соціальних потреб", year="2026", authors=["Ivanova, N."])]
    assert len(evidence.reference_list(cyrillic)) == 2  # a title in another script is still a title


def test_two_works_of_one_author_and_year_are_told_apart_by_letter_in_the_text_and_the_list():
    """Finding 1: "(Opok et al., 2026)" stood for two different papers, and the list gave no way to tell which."""
    financial = _source(url="https://doi.org/10.1/f", doi="10.1/f", title="Financial reward management and teachers' performance", year="2026",
                        authors=["Opok, J. B.", "Obici, I. G.", "Mwesigwa, D."], kind="ARTICLE", container="East African Journal of Education Studies")
    other = financial.model_copy(update={"url": "https://doi.org/10.1/n", "doi": "10.1/n", "title": "Non-financial reward management and teachers' performance"})
    alone = _source(url="https://example.org/s", title="A third study", year="2025", authors=["Smith, J."])
    library = _library(financial, other, alone)
    citer = evidence.Citer(library, "APA7", library)
    assert citer.render("Pay matters ⟦E000001⟧, and so does recognition ⟦E000002⟧.") == "Pay matters (Opok et al., 2026a), and so does recognition (Opok et al., 2026b)."
    assert citer.render("Both are reported ⟦E000001⟧ ⟦E000002⟧ ⟦E000003⟧.") == "Both are reported (Opok et al., 2026a; Opok et al., 2026b; Smith, 2025)."
    assert citer.render("⟦E000002|n⟧ disagree.") == "Opok et al. (2026b) disagree."
    listed = evidence.reference_list([i.source for i in library.values()])
    assert [entry[:44] for entry in listed] == ["Opok, J. B., Obici, I. G., & Mwesigwa, D. (2", "Opok, J. B., Obici, I. G., & Mwesigwa, D. (2", "Smith, J. (2025). A third study. https://exa"]
    assert "(2026a). Financial reward" in listed[0] and "(2026b). Non-financial reward" in listed[1]
    # a document that cites only one of them gives it no letter, in the text or in its list
    assert evidence.Citer(library, "APA7", ["E000001", "E000003"]).render("Pay matters ⟦E000001⟧.") == "Pay matters (Opok et al., 2026)."
    assert "(2026). Financial reward" in evidence.reference_list([financial, alone])[0]
    undated = [_source(url=f"https://example.org/{n}", title=title, year="", organisation="Microsoft", container="Microsoft") for n, title in enumerate(("About keyboard input", "Keyboard input overview"))]
    assert [evidence.reference(s, "APA7", letter)[:21] for s, letter in zip(undated, "ab", strict=True)] == ["Microsoft. (n.d.-a). ", "Microsoft. (n.d.-b). "]
    assert evidence.Citer(_library(*undated), "HARVARD", ["E000001", "E000002"]).render("See ⟦E000002⟧.") == "See (Microsoft n.d.-b)."


def test_authorship_is_never_changed_on_a_guess():
    """Finding 4: a group co-author, two people whose names use the same words, and two people who shorten alike
    were each lost."""
    from app.analysis.metadata import distinct_people, is_organisation

    assert clean_authors(["Smith, J.", "National Cancer Institute"]) == ["Smith, J.", "National Cancer Institute"]  # a body named on its own is a group author
    assert clean_authors(["Smith, J.", "Department of Epidemiology, National Cancer Institute, Bethesda"]) == ["Smith, J."]  # a unit with its place is where someone works
    assert clean_authors(["Smith, J.", "Smith, J."]) == ["Smith, J.", "Smith, J."]  # John and James
    assert clean_authors(["Ministry of Health", "Ministry of Health"]) == ["Ministry of Health"]
    assert distinct_people(["John Paul", "Paul John"]) == ["John Paul", "Paul John"]
    assert distinct_people(["John Smith", "James Smith"]) == ["John Smith", "James Smith"]
    assert distinct_people(["John Smith", "John Smith"]) == ["John Smith"] and distinct_people(["John Smith", "John Smith"], ["A1", "A2"]) == ["John Smith", "John Smith"]
    assert distinct_people(["John Smith", "John Smith"], ["A1", ""]) == ["John Smith"]
    assert distinct_people(["Conrad Murendo", "Meike Wollni", "Murendo Conrad", "Wollni Meike"], ["A1", "A2", "A3", "A4"]) == ["Conrad Murendo", "Meike Wollni"]
    works = fetch._openalex_works([{"display_name": "A study", "abstract_inverted_index": {"A": [0]}, "authorships": [
        {"author": {"display_name": "John Paul", "id": "https://openalex.org/A1"}}, {"author": {"display_name": "Paul John", "id": "https://openalex.org/A2"}},
        {"author": {"display_name": "John Smith", "id": "https://openalex.org/A3"}}, {"author": {"display_name": "James Smith", "id": "https://openalex.org/A4"}}]}])
    assert works[0]["authors"] == "Paul, J.; John, P.; Smith, J.; Smith, J."
    assert not is_organisation("John (Jack) Smith") and not is_organisation("Andrew The") and is_organisation("Center for Rapid Evidence Synthesis (ACRES)")
    registered = fetch._crossref_record({"title": ["Cancer statistics"], "author": [{"family": "Smith", "given": "John"}, {"name": "National Cancer Institute"}]})
    assert registered["authors"] == "Smith, J.; National Cancer Institute"


def test_only_a_name_that_says_so_is_a_repository():
    from app.analysis.metadata import clean_container

    for journal in ("Journal of Digital Repository Studies", "Archives of Disease in Childhood", "The Repository Review of Economics", "Research in Higher Education"):
        assert clean_container(journal) == journal, journal


def test_a_registration_that_names_no_author_is_completed_from_the_page(offline):
    """Finding 7: the registration was taken as it stood and the page, which named its author, was never read."""
    url = "https://www.sciencedirect.com/science/article/pii/S0001"
    offline.setattr(fetch, "resolve_doi", lambda u: "10.1016/j.x.2024.1")
    offline.setattr(fetch, "crossref_work", lambda doi: {"doi": doi, "title": "Uptake of the vaccine", "authors": "", "year": "2024", "container": "Vaccine", "volume": "42", "issue": "", "pages": "1–9"})
    offline.setattr(fetch, "page_meta", lambda u: {"title": "Uptake of the vaccine", "authors": "Smith, J.", "year": "2024", "container": "Vaccine", "volume": "42", "issue": "", "pages": "1–9", "doi": ""})
    source = pipeline._web_source(_Finding(url, title="Uptake of the vaccine", publisher="ScienceDirect", published="2024"))
    assert source.authors == ["Smith, J."] and source.doi == "10.1016/j.x.2024.1" and source.organisation == ""
    offline.setattr(fetch, "page_meta", lambda u: {})
    assert pipeline._web_source(_Finding(url, title="Uptake of the vaccine", publisher="ScienceDirect", published="2024")) is None  # a hosting site, and nobody named anywhere
    own = pipeline._web_source(_Finding("https://openknowledge.worldbank.org/handle/1", title="Uptake of the vaccine", publisher="World Bank", published="2024"))
    assert own.authors == [] and own.organisation == "World Bank"  # a body's own registered report is the body's


def test_a_site_is_judged_by_its_real_host_and_by_where_its_address_leads(offline):
    """Finding 9: "en.wikipedia.org." (a fully qualified name) passed, and a link that redirects was judged by the link."""
    assert pipeline._web_source(_Finding("https://en.wikipedia.org./wiki/Touchscreen", title="Touchscreen", publisher="Wikipedia", published="")) is None
    assert pipeline._web_source(_Finding("https://EN.WIKIPEDIA.ORG/wiki/Touchscreen", title="Touchscreen", publisher="Wikipedia", published="")) is None
    offline.setattr(fetch, "landed", lambda url: "https://en.wikipedia.org/wiki/Touchscreen" if "short.example" in url else url)
    assert pipeline._web_source(_Finding("https://short.example/abc", title="Touchscreen", publisher="Short", published="")) is None
    assert pipeline._web_source(_Finding("https://notwikipedia.org.example.com/a", title="A page", publisher="Example", published="2024")) is not None
