from prompt import user_message
from verify import answer_text, parse_reply, quote_found, verify_answer

SOURCES = [
    {"n": 1, "kind": "pc141", "title": "PC141 Lab Syllabus (Fall 2026)", "section": "Requirements and Policies > Plagiarism Policy", "pages": [4], "text": "• Consequences: plagiarism will result in a grade of zero on the affected lab."},
    {"n": 2, "kind": "pc141", "title": "PC141 Lab Announcements (MyLS)", "section": "Intro, Lab 1 > Laboratory Schedule", "pages": [2], "intro": "Laboratory sessions are held on alternate weeks in Room N2089.", "text": "PC141–L04 September 16 Wednesday 8:30 am – 10:20 am"},
    {"n": 3, "kind": "laurier", "authority": "policy", "title": "Policy 12.2 Student Code of Conduct", "section": "4.01 Academic Misconduct", "publisher": "Laurier University Policies", "text": "4.02.01 Plagiarism, which is the unacknowledged presentation of the work of others as one's own;"},
]


def answered(pc141=(), laurier=(), unverified=""):
    return verify_answer({"status": "answered", "pc141": list(pc141), "laurier": list(laurier), "unverified": unverified}, SOURCES)


def test_quotes_match_despite_pdf_spacing_dashes_and_ellipses():
    assert quote_found("PC141-L04 September 16 Wednesday 8:30 am - 10:20 am", [SOURCES[1]["text"]])
    assert quote_found("plagiarism will result in a grade of zero ... affected lab", [SOURCES[0]["text"]])
    assert not quote_found("plagiarism will result in a failing grade for the course", [SOURCES[0]["text"]])
    assert not quote_found("", [SOURCES[0]["text"]])


def test_multi_sentence_quotes_match_sentence_by_sentence_in_any_order():
    src = "16. Tutorial grades will be posted on MyLearningSpace (MyLS).\n17. The final tutorial grade will be determined out of 100%.\nMake-ups require a note. Make-ups are arranged within one week."
    assert quote_found("Tutorial grades will be posted on MyLearningSpace (MyLS). The final tutorial grade will be determined out of 100%.", [src])
    assert quote_found("Make‑ups are arranged within one week. Make‑ups require a note.", [src])
    assert not quote_found("Tutorial grades will be posted on MyLearningSpace (MyLS). The final grade is out of 90%.", [src])


def test_verified_claims_keep_their_bucket_and_the_answer_counts_as_answered():
    v = answered(
        pc141=[{"text": "Your L04 lab is Wednesday, September 16, 8:30 am to 10:20 am [2].", "quote": "PC141–L04 September 16 Wednesday 8:30 am – 10:20 am", "sources": [2]}],
        laurier=[{"text": "Plagiarism is presenting others' work as your own.", "quote": "the unacknowledged presentation of the work of others as one's own", "sources": [3]}],
        unverified="none",
    )
    assert v["status"] == "answered" and v["unverified"] == ""
    assert v["pc141"][0]["text"] == "Your L04 lab is Wednesday, September 16, 8:30 am to 10:20 am."
    assert v["pc141"][0]["verified"] and v["laurier"][0]["verified"]


def test_announcement_openings_count_as_part_of_the_cited_source():
    v = answered(pc141=[{"text": "Labs are held in Room N2089.", "quote": "held on alternate weeks in Room N2089", "sources": [2]}])
    assert v["pc141"][0]["verified"]


def test_uncited_claims_are_dropped_and_invented_numbers_are_flagged():
    v = answered(pc141=[
        {"text": "Late labs lose 10% per day.", "quote": "", "sources": []},
        {"text": "Plagiarism gets a grade of zero and a 2 week suspension.", "quote": "plagiarism will result in a grade of zero", "sources": [1]},
    ])
    assert v["status"] == "partial"
    assert len(v["pc141"]) == 1 and not v["pc141"][0]["verified"]
    assert '"2"' in v["pc141"][0]["issue"]
    assert "1 statement was removed" in v["unverified"]


def test_a_claim_citing_a_laurier_page_is_never_shown_as_a_pc141_rule():
    v = answered(pc141=[{"text": "Plagiarism is misconduct.", "quote": "Plagiarism, which is the unacknowledged presentation", "sources": [3]}])
    assert v["pc141"] == [] and len(v["laurier"]) == 1


def test_a_claim_mixing_course_and_university_sources_is_flagged_and_filed_where_its_quote_is_from():
    v = answered(laurier=[{"text": "Plagiarism means a zero on the lab and is presenting others' work as your own.", "quote": "plagiarism will result in a grade of zero", "sources": [1, 3]}])
    assert v["laurier"] == [] and len(v["pc141"]) == 1
    assert not v["pc141"][0]["verified"]
    assert "mixes a PC141 rule with a university rule" in v["pc141"][0]["issue"]
    assert v["status"] == "partial"


def test_ones_own_is_not_read_as_the_number_1():
    v = answered(laurier=[{"text": "Plagiarism is presenting others' work as one's own.", "quote": "the unacknowledged presentation of the work of others as one's own", "sources": [3]}])
    assert v["laurier"][0]["verified"], v["laurier"][0].get("issue")


def test_no_supported_claims_means_not_found_with_an_explanation():
    v = answered(pc141=[{"text": "The final is worth 40%.", "quote": "final exam 40%", "sources": [9]}])
    assert v["status"] == "not_found" and v["unverified"]
    assert answer_text(v).startswith("Could not verify:")


def test_malformed_replies_are_handled():
    assert parse_reply('```json\n{"status": "answered"}\n```') == {"status": "answered"}
    assert parse_reply("not json") is None
    v = verify_answer({"pc141": "oops", "laurier": [None, {"text": "x", "sources": ["a"]}]}, SOURCES)
    assert v["status"] == "not_found"


def test_the_prompt_labels_each_source_with_its_kind_and_section():
    msg = user_message("When is my lab?", SOURCES)
    assert "[2] PC141 | PC141 Lab Announcements (MyLS) > Intro, Lab 1 > Laboratory Schedule, p. 2\n(Announcement opening: Laboratory sessions" in msg
    assert "[3] LAURIER, university policy | Policy 12.2 Student Code of Conduct > 4.01 Academic Misconduct (Laurier University Policies)" in msg
    assert msg.endswith("Question: When is my lab?")
