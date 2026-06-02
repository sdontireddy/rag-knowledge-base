from services.api.services.answer_prompt import STRICT_RAG_BEHAVIOR_RULES, build_strict_rag_prompt


def test_strict_prompt_contains_confinement_rules() -> None:
    prompt = build_strict_rag_prompt(
        query="How do I configure Bedrock?",
        context_chunks=[
            {
                "chunk_id": "c1",
                "source_path": "AWS/Bedrock.md",
                "domain": "AWS",
                "section": "AWS > Bedrock",
                "text": "Enable model access in the AWS console before using Bedrock.",
            }
        ],
    )

    assert STRICT_RAG_BEHAVIOR_RULES in prompt
    assert "Use only the information explicitly present in the provided context chunks." in prompt
    assert "Do not use prior knowledge, world knowledge, training knowledge, or unstated assumptions." in prompt
    assert "If the context does not contain enough information to answer, reply exactly: INSUFFICIENT_CONTEXT." in prompt
    assert "Every factual statement in the answer must include at least one citation" in prompt
    assert "[c1]" in prompt
    assert "Enable model access in the AWS console before using Bedrock." in prompt


def test_strict_prompt_includes_all_context_chunks_and_question() -> None:
    prompt = build_strict_rag_prompt(
        query="Summarize the deployment prerequisites.",
        context_chunks=[
            {
                "chunk_id": "aws-1",
                "source_path": "AWS/CloudFront.md",
                "domain": "AWS",
                "section": "AWS > CloudFront",
                "text": "Create the distribution before updating DNS.",
            },
            {
                "chunk_id": "mawm-9",
                "source_path": "MAWM/Deployment.md",
                "domain": "MAWM",
                "section": "MAWM > Deployment",
                "text": "Validate firewall access before promoting to QA.",
            },
        ],
    )

    assert "Summarize the deployment prerequisites." in prompt
    assert "[aws-1]" in prompt
    assert "[mawm-9]" in prompt
    assert "Create the distribution before updating DNS." in prompt
    assert "Validate firewall access before promoting to QA." in prompt


def test_strict_prompt_handles_missing_context() -> None:
    prompt = build_strict_rag_prompt(query="What is the rollback plan?", context_chunks=[])

    assert "[NO_CONTEXT]" in prompt
    assert "No context chunks were retrieved." in prompt
    assert "INSUFFICIENT_CONTEXT" in prompt