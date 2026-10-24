import json, os, re
from pathlib import Path
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DATA = Path("data/courses.json")
HSE_FALLBACK = "https://www.hse.ru/ba/isct/courses?course=1.1.1.4&page=1&year=2026"

st.set_page_config(page_title="Помощник первокурсника ИВТ МИЭМ", page_icon="🎓", layout="wide")

@st.cache_data
def load_data():
    if not DATA.exists():
        return []
    return json.loads(DATA.read_text(encoding="utf-8"))

courses = load_data()
if not courses:
    st.warning("Локальный индекс не найден. Запустите `python ingest.py`.")
    st.stop()

docs, meta = [], []
for c in courses:
    for ch in c["chunks"]:
        docs.append(f"Дисциплина: {c['title']}\nРаздел: {ch['section']}\n{ch['text']}")
        meta.append((c, ch))

@st.cache_resource
def make_index(texts):
    v = TfidfVectorizer(ngram_range=(1,2), min_df=1, max_df=0.98)
    X = v.fit_transform(texts)
    return v, X

vectorizer, X = make_index(docs)

SYSTEM = """Ты — помощник первокурсника ИВТ МИЭМ НИУ ВШЭ.
Отвечай только на основании переданных фрагментов программ дисциплин 2026/2027.
Не додумывай расписание, преподавателей, дедлайны, аудитории или правила, которых нет в источниках.
Если данных недостаточно, прямо скажи об этом.
Ответ должен быть кратким (обычно 2–5 предложений). В конце перечисли источники в виде названия дисциплины и URL."""

def retrieve(q, k=6):
    qv = vectorizer.transform([q])
    scores = cosine_similarity(qv, X).ravel()
    idx = scores.argsort()[::-1][:k]
    return [(float(scores[i]), meta[i][0], meta[i][1]) for i in idx if scores[i] > 0.05]

def llm_answer(question, hits):
    try:
        from openai import OpenAI
        client = OpenAI()
        context = "\n\n---\n\n".join(
            f"[{c['title']} | {ch['section']} | {c['url']}]\n{ch['text']}"
            for _, c, ch in hits
        )
        prompt = f"{SYSTEM}\n\nВопрос студента:\n{question}\n\nМатериалы:\n{context}"
        r = client.responses.create(model=os.getenv("OPENAI_MODEL","gpt-5-mini"), input=prompt)
        return r.output_text.strip()
    except Exception:
        return None

st.title("🎓 Помощник первокурсника ИВТ МИЭМ")
st.caption("Срез учебных программ НИУ ВШЭ: 2026/2027, 1 курс")

q = st.text_area("Ваш вопрос", placeholder="Например: Какие темы изучаются в «Алгоритмизации и программировании»?")
if st.button("Ответить", type="primary") and q.strip():
    hits = retrieve(q)
    if not hits:
        st.info("В локальном корпусе не найдено достаточно релевантных материалов. Попробуйте назвать дисциплину.")
        st.stop()

    answer = llm_answer(q, hits)
    if answer:
        st.markdown("### Ответ")
        st.write(answer)
    else:
        st.markdown("### Найденные материалы")
        # Safe fallback: extractive response, no invented synthesis.
        for score, c, ch in hits[:3]:
            st.markdown(f"**{c['title']} — {ch['section']}**")
            st.write(ch["text"][:1200])

    st.markdown("### Источники")
    seen = set()
    for score, c, ch in hits:
        if c["url"] not in seen:
            st.markdown(f"- [{c['title']}]({c['url']}) — раздел `{ch['section']}`, релевантность {score:.2f}")
            seen.add(c["url"])

with st.sidebar:
    st.header("О решении")
    st.write(f"В индексе: {len(courses)} дисциплин, {len(docs)} фрагментов.")
    st.write("RAG: retrieval → контекст → LLM → ответ + источники.")
    st.link_button("Каталог HSE 2026/2027", HSE_FALLBACK)
