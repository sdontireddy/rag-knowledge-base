"""Streamlit UI for retrieval-grounded question answering."""

from __future__ import annotations

import os
import re

import streamlit as st

from services.ui.local_rag_client import LocalRagApiError, LocalRagClient


API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8080").rstrip("/")
UI_ANSWER_TIMEOUT_SECONDS = float(os.getenv("UI_ANSWER_TIMEOUT_SECONDS", "90"))


@st.cache_resource
def _rag_client() -> LocalRagClient:
	return LocalRagClient(
		base_url=API_BASE_URL,
		answer_timeout_seconds=UI_ANSWER_TIMEOUT_SECONDS,
	)


def _format_answer_markdown(answer_text: str) -> str:
	cleaned = " ".join((answer_text or "").split())
	if not cleaned:
		return ""

	# Improve readability for model outputs that collapse sentence spacing.
	cleaned = re.sub(r"([.!?])(\[)", r"\1 \2", cleaned)
	cleaned = re.sub(r"([.!?])([A-Z\"])", r"\1 \2", cleaned)
	cleaned = cleaned.replace('""', '"')

	segments = [segment.strip() for segment in re.split(r"(?<=\])\s+|(?<=[.!?])\s+", cleaned) if segment.strip()]
	if not segments:
		segments = [cleaned]

	group_order = [
		"API Design",
		"Integration",
		"Reliability & Performance",
		"Security",
		"Delivery & Governance",
		"Other",
	]
	groups: dict[str, list[str]] = {name: [] for name in group_order}

	for segment in segments:
		bucket = _classify_segment(segment)
		groups[bucket].append(segment)

	sections: list[str] = ["### Key Points"]
	for heading in group_order:
		items = groups[heading]
		if not items:
			continue
		sections.append(f"#### {heading}")
		sections.extend(f"- {item}" for item in items)

	return "\n".join(sections)


def _classify_segment(text: str) -> str:
	lower = text.lower()

	if any(token in lower for token in ["contract-first", "resource", "rest", "grpc", "api design", "versioning"]):
		return "API Design"

	if any(token in lower for token in ["event-driven", "orchestration", "integration", "exception handling", "async"]):
		return "Integration"

	if any(token in lower for token in ["timeout", "retry", "jitter", "idempotency", "rate limit", "reliability", "performance", "observability"]):
		return "Reliability & Performance"

	if any(token in lower for token in ["oauth", "oidc", "auth", "security", "validation"]):
		return "Security"

	if any(token in lower for token in ["governance", "checkpoint", "risk", "delivery", "roadmap", "release"]):
		return "Delivery & Governance"

	return "Other"


def _get_domains() -> list[str]:
	try:
		return _rag_client().domains()
	except LocalRagApiError:
		return []


def _answer_question(query: str, domain_filter: list[str], k: int, max_tokens: int) -> dict:
	return _rag_client().ask(
		query=query,
		domain_filter=domain_filter,
		k=k,
		max_tokens=max_tokens,
	)


st.set_page_config(page_title="RAG Knowledge Base", layout="wide")
st.title("RAG Knowledge Base")
st.caption("Answers are restricted to retrieved vector-store context and must cite chunk IDs.")

domains = _get_domains()

with st.form("answer-form"):
	query = st.text_area("Question", placeholder="Ask a question grounded in your indexed notes", height=120)
	selected_domains = st.multiselect("Domain filter", options=domains)
	k = st.slider("Retrieved chunks", min_value=1, max_value=10, value=5)
	max_tokens = st.slider("Max answer tokens", min_value=128, max_value=2048, value=256, step=64)
	submitted = st.form_submit_button("Generate answer")

if submitted:
	if not query.strip():
		st.error("Enter a question.")
	else:
		try:
			payload = _answer_question(query=query.strip(), domain_filter=selected_domains, k=k, max_tokens=max_tokens)
		except LocalRagApiError as exc:
			st.error(f"Answer request failed: {exc}")
		else:
			st.subheader("Answer")
			answer_text = payload.get("answer_text", "")
			if answer_text == "INSUFFICIENT_CONTEXT":
				st.warning("INSUFFICIENT_CONTEXT")
				if payload.get("generation_time_ms", 0) == 0 and payload.get("context_chunks"):
					st.info("Answer generation timed out. Try reducing Max answer tokens or increase ANSWER_TIMEOUT_SECONDS.")
			else:
				st.markdown(_format_answer_markdown(answer_text))

			st.caption(
				f"Model: {payload.get('model', 'unknown')} | Generation time: {payload.get('generation_time_ms', 0)} ms"
			)

			st.subheader("Citations")
			citations = payload.get("citations", [])
			if not citations:
				st.write("No citations returned.")
			else:
				for citation in citations:
					st.markdown(
						f"- [{citation['chunk_id']}] {citation['source_path']} | {citation['section']} | score={citation['relevance_score']:.3f}"
					)

			st.subheader("Supporting Chunks")
			context_chunks = payload.get("context_chunks", [])
			if not context_chunks:
				st.write("No context chunks returned.")
			else:
				for idx, chunk in enumerate(context_chunks, start=1):
					with st.expander(
						f"{idx}. [{chunk['chunk_id']}] {chunk['source_path']} | {chunk['section']} | score={chunk['relevance_score']:.3f}"
					):
						st.write(chunk.get("text", ""))
