"""Turn an official Laurier web page into citable sections.

Handles the page templates of wlu.ca policies, students.wlu.ca and academic-calendar.wlu.ca:

- Headings (h2-h4, the Calendar's <div class="heading"> and month rows) become the section path,
  e.g. "4.04 Penalties for Academic Misconduct". Numbered headings nest by their number.
- Tables with column headers (Policy 12.2's penalty grid) become "Row – Column: cell" lines, so a
  penalty stays attached to "First Offence". Two-column rows become "a – b".
- Calendar date tables become "September 1, 2026: Classes begin" lines.
- Long sections are split into parts of at most MAX_CHARS, preferring to break before a numbered
  clause; each part records the clauses it holds ("4.02.04–4.02.09") and a link that scrolls to it.
"""
import re
from urllib.parse import quote

from bs4 import BeautifulSoup, Comment, NavigableString

MAX_CHARS = 1500  # about 350 tokens, well under the embedding model's 512
MIN_TAIL = 250  # a last part shorter than this joins the one before it
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
CLAUSE = re.compile(r"^(?:•\s*)?(\d{1,2}\.\d{2}(?:\.\d{2})*)\b")
BOILERPLATE = [re.compile(r"^Print \| PDF$", re.I), re.compile(r"^This online version is for convenience", re.I)]
BLOCKS = "p div ul ol tr table thead tbody br hr section article header footer aside h5 h6 dd dt dl blockquote pre figure figcaption summary details caption".split()
H = "\x01"  # marks a heading line: H level H anchor H text


def squash(text):
    return re.sub(r"\s+", " ", text).strip()


def content_region(soup):
    """The page's main content, without site navigation, sidebars and footers."""
    for selector in ["main", "#maincontent", "div.content", "body"]:  # div.content: the Calendar
        if region := soup.select_one(selector):
            return region
    return soup


def page_title(html):
    soup = BeautifulSoup(html, "html.parser")
    if h1 := content_region(soup).find("h1"):
        return squash(h1.get_text(" "))
    return squash(soup.title.get_text()).split(" | ")[0] if soup.title else ""


def revised_date(html):
    """A policy's "Date of Most Recent Review/Revision", or None."""
    text = squash(BeautifulSoup(html, "html.parser").get_text(" "))
    m = re.search(r"Date of Most Recent Review/Revision\s*:\s*(.+?)(?=\s+(?:Office of Accountability|Administrative Responsibility|Approving Authority|\d\.00)\b|$)", text)
    revised = m.group(1).strip()[:120] if m else None
    return None if not revised or re.fullmatch(r"n/?a", revised, re.I) else revised


def linearize_table(table):
    """Rows of a table whose first row is all column headers (three or more, no merged cells) as
    "Row – Column: cell" lines; None for any other table."""
    rows = [tr.find_all(["th", "td"]) for tr in table.find_all("tr")]
    head = rows[0] if rows else []
    if len(rows) < 2 or len(head) < 3 or not all(c.name == "th" for c in head):
        return None
    if any(len(r) != len(head) or any(c.get("colspan") or c.get("rowspan") for c in r) for r in rows):
        return None
    lines = [squash(table.caption.get_text(" "))] if table.caption else []
    for row in rows[1:]:
        row_head = squash(row[0].get_text(" ")) if row[0].name == "th" else ""
        for j, cell in enumerate(row):
            if j == 0 and cell.name == "th":
                continue
            items = [squash(li.get_text(" ")) for li in cell.find_all("li")]
            value = " ".join(i for i in items if i) or squash(cell.get_text(" "))
            if value:
                lines.append(f"{' – '.join(x for x in [row_head, squash(head[j].get_text(' '))] if x)}: {value}")
    return lines


def heading_marker(soup, level, tag):
    text = squash(tag.get_text(" "))
    anchor = tag.get("id") or next((a.get("id") or a.get("name") for a in tag.find_all("a") if a.get("id") or a.get("name")), "")
    return NavigableString(f"\n{H}{level}{H}{anchor}{H}{text}\n" if text else " ")


def page_lines(html):
    """The page's content as text lines, with headings marked by H."""
    soup = BeautifulSoup(html, "html.parser")
    region = content_region(soup)
    for tag in region.select("script, style, noscript, svg, nav, form, iframe, template, h1, #contentRHS, .returntotop, ul.breadcrumbs"):
        tag.decompose()
    for div in region.select("div.greyheading"):  # the Calendar's "Anchors"/"Months" jump lists
        if (jump := div.find_next_sibling("ul")) is not None:
            jump.decompose()
        div.decompose()
    for ul in region.find_all(["ul", "ol"]):  # unlabelled breadcrumbs
        first = ul.find("li")
        if first and first.find("a") and squash(first.get_text()) == "Home":
            ul.decompose()
    for comment in region.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    # Newlines in the HTML source are not line breaks; only the tags below are.
    for s in region.find_all(string=True):
        s.replace_with(re.sub(r"\s+", " ", s))

    for table in region.find_all("table"):
        if (lines := linearize_table(table)) is not None:
            table.replace_with(NavigableString("".join(f"\n{line}\n" for line in lines)))
    for th in region.find_all("th"):  # Calendar month rows: <th><a name="26-09"></a>September, 2026</th>
        if th.find("a", attrs={"name": True}):
            th.replace_with(heading_marker(soup, 2, th))
    for tr in region.find_all("tr"):
        cells = [text for c in tr.find_all(["td", "th"]) if (text := squash(c.get_text(" ")))]
        if cells:
            tr.replace_with(NavigableString(f"\n{' – '.join(cells)}\n"))
    for div in region.select("div.heading"):  # Calendar section headings
        div.replace_with(heading_marker(soup, 2, div))
    for tag in region.find_all(["h2", "h3", "h4"]):
        tag.replace_with(heading_marker(soup, int(tag.name[1]), tag))
    for li in region.find_all("li"):
        li.insert(0, NavigableString("\n• "))
    for tag in region.find_all(BLOCKS):
        tag.insert_before(NavigableString("\n"))
        tag.insert_after(NavigableString("\n"))
    return [squash(line) for line in region.get_text().split("\n")]


def raw_sections(html):
    """[{path, anchor, heading, text}] in page order, one per heading."""
    sections, stack, lines = [], [], []

    def flush():
        text = "\n".join(lines).strip()
        lines.clear()
        if text:
            path = [h["text"] for h in stack] or ["Overview"]
            top = stack[-1] if stack else {"anchor": "", "text": ""}
            sections.append({"path": path, "anchor": top["anchor"], "heading": top["text"], "text": text})

    for line in page_lines(html):
        if line.startswith(H):
            _, level, anchor, text = line.split(H)
            flush()
            while stack and stack[-1]["level"] >= int(level):
                stack.pop()
            stack.append({"level": int(level), "anchor": anchor, "text": text})
        elif line and line != "•" and not re.fullmatch(r"[–\s]+", line):
            lines.append(line)
    flush()
    return sections


def dates_to_sentences(section):
    """Under a "September, 2026" heading, "1 – Classes begin" becomes "September 1, 2026: Classes begin"."""
    m = re.fullmatch(rf"({MONTHS}),? (\d{{4}})", section["heading"])
    if m:
        month, year = m.groups()
        text = re.sub(r"^(\d{1,2}) – (.*)$", rf"{month} \1, {year}: \2", section["text"], flags=re.M)
        section["text"] = re.sub(r"^([A-Z][a-z]{2} \d{1,2} - [A-Z][a-z]{2} \d{1,2}) – (.*)$", rf"\1, {year}: \2", text, flags=re.M)
    return section


def clause_number(heading):
    """ "4.01.02 Right of Access" -> [4, 1, 2]; "4.00 Policy" -> [4]; anything else -> None."""
    m = re.match(r"^(\d{1,2})\.(\d{2})((?:\.\d{2})*)\b", heading)
    if not m:
        return None
    parts = [int(m.group(1)), int(m.group(2)), *(int(x) for x in m.group(3).split(".") if x)]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return parts


def fix_numbered_path(path):
    """Policy pages mix heading levels, so "5.00 Roles" can land under "4.00 Policy". A numbered
    heading stays above another numbered heading only when its number is a prefix of the other's."""
    out = []
    for h in path:
        n = clause_number(h)
        while n and out:
            last = clause_number(out[-1])
            if not last or (len(last) < len(n) and n[: len(last)] == last):
                break
            out.pop()
        out.append(h)
    return out


def wrap_line(line, limit):
    parts = []
    while len(line) > limit:
        head = line[:limit]
        cut = head.rfind(". ") + 1 if head.rfind(". ") > limit / 3 else head.rfind(" ") if head.rfind(" ") > 0 else limit
        parts.append(line[:cut].strip())
        line = line[cut:].strip()
    return [*parts, line]


def split_text(text, limit=MAX_CHARS):
    """Parts of about equal size, none over `limit`. Once a part is most of the way to its share,
    it ends before the next numbered clause, so parts start where the policy's numbering does."""
    if len(text) <= limit:
        return [text]
    lines = [p for line in text.split("\n") for p in wrap_line(line, limit)]
    target = len(text) / -(-len(text) // limit)
    parts, buf, size = [], [], 0
    for line in lines:
        add = len(line) + (1 if buf else 0)
        if buf and (size + add > limit or (size >= target * 0.7 and size + add > target and CLAUSE.match(line))):
            parts.append("\n".join(buf))
            buf, size = [], 0
            add = len(line)
        buf.append(line)
        size += add
    if buf:
        parts.append("\n".join(buf))
    if len(parts) > 1 and len(parts[-1]) < MIN_TAIL and len(parts[-2]) + len(parts[-1]) < limit * 1.2:
        tail = parts.pop()
        parts[-1] += "\n" + tail
    return parts


def clause_range(text):
    """The numbered clauses a part holds: "4.02.04–4.02.09", "5.03", or ""."""
    nums = [m.group(1) for line in text.split("\n") if (m := CLAUSE.match(line))]
    if not nums:
        return ""
    return nums[0] if nums[0] == nums[-1] else f"{nums[0]}–{nums[-1]}"


def text_fragment(words):
    """A #:~:text= link that scrolls to and highlights `words` on the page."""
    return "#:~:text=" + quote(words, safe="!~*'()").replace("-", "%2D")


def deep_link(url, section, part_text, part_index):
    if part_index == 0 and section["anchor"]:
        return f"{url}#{section['anchor']}"
    heading = section["heading"]
    if part_index == 0 and heading and (len(heading.split()) >= 3 or re.search(r"\d", heading)):
        return url + text_fragment(heading)  # "Policy" or "Purpose" occurs many times on a page
    if part_index == 0 and not heading:
        return url
    first = part_text.split("\n")[0].split(" – ")[0]  # "a – b" table rows exist only in our text
    words = " ".join(re.sub(r"^•\s*", "", first).split()[:6])
    return url + text_fragment(re.sub(r"[\s,;:–—-]+$", "", words))


def page_sections(html, page):
    """The page's citable sections: [{section, url, text}], ready for the corpus."""
    title = page["title"]
    merged = []  # sections that share a path and anchor are one section, split again below
    for sec in raw_sections(html):
        if merged and merged[-1]["path"] == sec["path"] and merged[-1]["anchor"] == sec["anchor"]:
            merged[-1]["text"] += "\n" + sec["text"]
        else:
            merged.append(sec)
    out = []
    for sec in map(dates_to_sentences, merged):
        lines = [l for l in sec["text"].split("\n") if l.strip() and l.strip() != title and not any(b.match(l.strip()) for b in BOILERPLATE)]
        text = "\n".join(lines).strip()
        if not text:
            continue
        path = fix_numbered_path(sec["path"])
        for i, part in enumerate(split_text(text)):
            clauses = clause_range(part)
            section = " > ".join(path)
            if clauses and not path[-1].startswith(f"{clauses} "):
                section += f" ({clauses})"
            out.append({"section": section, "url": deep_link(page["url"], sec, part, i), "text": part})
    return out
