"""What goes into the assistant's corpus: the PC141 PDFs and the official Laurier pages.

Edit this file to add or drop a document, then run `python scripts/build_corpus.py`.
"""

# PC141 documents in files/, with the names shown in citations.
PDFS = {
    "PC141LabSyllabus2026FRAG.pdf": "PC141 Lab Syllabus (Fall 2026)",
    "PC141labRules.pdf": "PC141 Lab Announcements (MyLS)",
    "PC141tutorialRules.pdf": "PC141 Tutorial Announcements (MyLS)",
    "PC141labRAG.pdf": "PC141 Lab Manual: Estimation and Bounding",
}

CALENDAR = "Undergraduate Academic Calendar 2026/27"
POLICIES = "Laurier University Policies"
_cal = "https://academic-calendar.wlu.ca/"
_students = "https://students.wlu.ca/"
_policy = "https://www.wlu.ca/about/governance/assets/resources/"

# Official Laurier pages a PC141 student is likely to need: the Academic Calendar's rules and
# dates, the student pages that explain them, and the university policies on academic integrity,
# accommodation, conduct, safety and student records. Policies take their title from the page.
LAURIER_PAGES = [
    # Academic Calendar
    {"id": "exams", "title": "Examinations", "publisher": CALENDAR, "url": _cal + "section.php?cal=1&s=1174&sp=3905&ss=4668&y=93"},
    {"id": "grades", "title": "Grades", "publisher": CALENDAR, "url": _cal + "section.php?cal=1&s=1174&sp=3904&ss=4668&y=93"},
    {"id": "add-drop", "title": "Adding and Dropping Courses", "publisher": CALENDAR, "url": _cal + "section.php?cal=1&s=1174&sp=3893&ss=4667&y=93"},
    {"id": "petitions", "title": "Faculty Petitions", "publisher": CALENDAR, "url": _cal + "section.php?cal=1&s=1174&sp=3910&ss=4669&y=93"},
    {"id": "student-regulations", "title": "Student Regulations", "publisher": CALENDAR, "url": _cal + "section.php?cal=1&s=1174&sp=3919&ss=4671&y=93"},
    {"id": "dates-fall", "title": "Academic & Related Dates: Fall Term 2026 (12-week courses)", "publisher": CALENDAR, "url": _cal + "dates.php?cal=1&t=462&y=93"},
    {"id": "dates-winter", "title": "Academic & Related Dates: Winter Term 2027 (12-week courses)", "publisher": CALENDAR, "url": _cal + "dates.php?cal=1&t=463&y=93"},
    # Student pages
    {"id": "misconduct-defined", "title": "Academic Misconduct Defined", "publisher": "Laurier Students: Academic Integrity", "url": _students + "academics/support-and-advising/academic-integrity/types-of-academic-misconduct.html"},
    {"id": "misconduct-procedures", "title": "Academic Misconduct Procedures", "publisher": "Laurier Students: Academic Integrity", "url": _students + "academics/support-and-advising/academic-integrity/academic-misconduct-procedures.html"},
    {"id": "gen-ai", "title": "Gen AI Student Resource Hub", "publisher": "Laurier Students: Academic Integrity", "url": _students + "academics/support-and-advising/academic-integrity/gen-ai-student-resource-hub.html"},
    {"id": "deferred-exams", "title": "Deferred Exams", "publisher": "Laurier Students: Exams", "url": _students + "academics/exams/deferred-exams.html"},
    {"id": "disruptions", "title": "Managing Unexpected Academic Disruptions", "publisher": "Laurier Students: Dean of Students", "url": _students + "support-and-wellness/student-affairs/dean-of-students/assets/resources/managing-unexpected-academic-disruptions.html"},
    {"id": "petitions-appeals", "title": "Academic Petitions and Appeals", "publisher": "Laurier Students: Calendars and Petitions", "url": _students + "academics/support-and-advising/calendars-and-petitions/petitions-and-appeals/index.html"},
    {"id": "accessible-learning", "title": "Accessible Learning", "publisher": "Laurier Students: Accessible Learning", "url": _students + "academics/support-and-advising/accessible-learning/index.html"},
    # University policies and their procedures
    {"id": "policy-12-2", "title": "Policy 12.2 Student Code of Conduct: Academic Misconduct", "publisher": POLICIES, "url": _policy + "12.2-student-code-of-conduct.html"},
    {"id": "procedures-12-2", "publisher": POLICIES, "url": _policy + "procedures-for-student-code-of-conduct.html"},
    {"id": "policy-2-3", "title": "Policy 2.3 Academic Accommodation of Students with Disabilities", "publisher": POLICIES, "url": _policy + "2.3-academic-accommodation-of-students-with-disabilities.html"},
    {"id": "procedures-2-3", "publisher": POLICIES, "url": _policy + "procedures-for-undergraduate-and-graduate-student-accommodations-2.3.html"},
    {"id": "policy-2-5", "publisher": POLICIES, "url": _policy + "2.5-policy-on-academic-disruption.html"},
    {"id": "policy-6-1", "publisher": POLICIES, "url": _policy + "6.1-prevention-of-harassment-and-discrimination.html"},
    {"id": "procedures-6-1", "publisher": POLICIES, "url": _policy + "procedures-relating-to-the-prevention-of-harassment-and-discrimination-policy-6.1.html"},
    {"id": "policy-7-6", "publisher": POLICIES, "url": _policy + "7.6-severe-weather-storm-closing.html"},
    {"id": "procedures-7-6", "publisher": POLICIES, "url": _policy + "procedures-relating-to-policy-on-university-closing-due-to-severe-weather-7.6.html"},
    {"id": "policy-7-16", "publisher": POLICIES, "url": _policy + "7.16-laboratory-health-and-safety.html"},
    {"id": "policy-9-3", "publisher": POLICIES, "url": _policy + "9.3-classroom-use-of-electronic-devices.html"},
    {"id": "policy-9-6", "publisher": POLICIES, "url": _policy + "9.6-use-procurement-and-developmnt-of-generative-artificial-intelligence.html"},
    {"id": "policy-10-2", "publisher": POLICIES, "url": _policy + "10.2-student-records.html"},
    {"id": "policy-10-2-appendix-a", "publisher": POLICIES, "url": _policy + "10.2-appendix-a-documents-included-in-the-student-academic-record-and-official-academic-transcript.html"},
    {"id": "policy-12-3", "publisher": POLICIES, "url": _policy + "12.3-non-academic-student-code-of-conduct.html"},
    {"id": "procedures-12-3", "publisher": POLICIES, "url": _policy + "procedures-for-non-academic-student-code-of-conduct.html"},
    {"id": "policy-12-4", "publisher": POLICIES, "url": _policy + "12.4-gendered-and-sexual-violence-policy.html"},
    {"id": "procedures-12-4", "publisher": POLICIES, "url": _policy + "procedures-relating-to-gendered-and-sexual-violence-policy-12.4.html"},
    {"id": "policy-12-5", "publisher": POLICIES, "url": _policy + "12.5-student-mental-health-policy.html"},
    {"id": "procedures-12-5", "publisher": POLICIES, "url": _policy + "procedures-for-student-mental-health-policy-12.5.html"},
]


def authority(url):
    """How much weight a page carries: policies and the Calendar are the rules, other pages explain them."""
    if url.startswith("https://www.wlu.ca/about/governance/"):
        return "policy"
    if url.startswith("https://academic-calendar.wlu.ca/"):
        return "calendar"
    return "guidance"
