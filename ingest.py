import json, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

BASE = "https://www.hse.ru"
CATALOG_URLS = [
    "https://www.hse.ru/ba/isct/courses?course=1.1.1.4&page=1&year=2026",
    "https://www.hse.ru/ba/isct/courses?course=1.1.1.4&page=2&year=2026",
]
OUT = Path("data/courses.json")

HEADERS = {"User-Agent": "Mozilla/5.0 (MIEM freshman assistant prototype)"}

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def course_links(html):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE, a["href"])
        if "/ba/isct/courses/" in href and href.endswith(".html"):
            links.add(href.split("#")[0])
    return sorted(links)

def parse_course(url):
    soup = BeautifulSoup(get(url), "html.parser")
    text = soup.get_text("\n", strip=True)
    title = clean(soup.find("h1").get_text(" ", strip=True)) if soup.find("h1") else url

    def between(start, ends):
        pos = text.find(start)
        if pos < 0: return ""
        pos += len(start)
        endpos = len(text)
        for e in ends:
            p = text.find(e, pos)
            if p >= 0: endpos = min(endpos, p)
        return clean(text[pos:endpos])

    # The page has a stable human-readable pattern. We retain the raw text too,
    # so minor HSE markup changes do not destroy the local corpus.
    year = "2026/2027" if "2026/2027" in text else ""
    when = between("Когда читается:", ["Преподаватели", "Программа дисциплины"])
    if "1-й курс" not in when:
        return None

    credits = ""
    m = re.search(r"\n(\d+)\nКредиты", text)
    if m: credits = m.group(1)

    status = between("Статус:", ["Когда читается:"])
    language = between("Язык:", ["Кредиты:", "Контактные часы:", "Программа дисциплины"])
    annotation = between("Аннотация", ["Цель освоения дисциплины"])
    goal = between("Цель освоения дисциплины", ["Планируемые результаты обучения"])
    outcomes = between("Планируемые результаты обучения", ["Содержание учебной дисциплины"])
    content = between("Содержание учебной дисциплины", ["Элементы контроля", "Промежуточная аттестация", "Список литературы"])
    control = between("Элементы контроля", ["Промежуточная аттестация", "Список литературы"])
    attestation = between("Промежуточная аттестация", ["Список литературы"])
    literature = between("Список литературы", ["Презентации", "Авторы", "О ВЫШКЕ"])

    # Extract headings/paragraph-ish lines as lightweight evidence chunks.
    chunks = []
    for section, value in [
        ("annotation", annotation), ("goal", goal), ("outcomes", outcomes),
        ("content", content), ("control", control),
        ("attestation", attestation), ("literature", literature)
    ]:
        if value:
            chunks.append({"section": section, "text": value})

    return {
        "title": title, "year": year, "when": when, "credits": credits,
        "status": status, "language": language, "url": url,
        "chunks": chunks, "raw_text": clean(text)
    }

def main():
    all_links = set()
    for u in CATALOG_URLS:
        try:
            all_links.update(course_links(get(u)))
        except Exception as e:
            print("catalog error", u, e)

    courses = []
    for i, url in enumerate(sorted(all_links), 1):
        try:
            item = parse_course(url)
            if item:
                courses.append(item)
                print(f"[{i}/{len(all_links)}] {item['title']}")
        except Exception as e:
            print("skip", url, e)
        time.sleep(0.1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(courses, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(courses)} first-year courses to {OUT}")

if __name__ == "__main__":
    main()
