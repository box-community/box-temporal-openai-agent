import pytest
from box_sdk_gen import AiItemAskTypeField, CreateAiAskMode

from activities.box_publish import _box_ai_file_ids, _box_ai_request, format_box_ai_digest
from agents.shared import BoxAIDigest, BoxAIReviewRequest


def test_format_box_ai_digest() -> None:
    digest = BoxAIDigest(
        answer={
            "executiveDigest": "A concise signal.",
            "externalSignals": ["market change"],
            "internalSignals": ["campaign performance"],
            "alignments": ["festival partnerships"],
            "tensions": ["streaming discovery differs"],
            "markets": ["Poland", "France"],
            "recommendedActions": ["Validate creator partnerships"],
            "confidenceNotes": "Evidence is well sourced.",
            "followUpQuestions": ["What changes next quarter?"],
        },
        citations=[
            {
                "id": "123",
                "type": "file",
                "name": "internal-retrospective.txt",
                "content": "The campaign used festival partnerships.",
            }
        ],
        completion_reason="done",
    )

    markdown = format_box_ai_digest(digest)

    assert "# Box AI Research Digest" in markdown
    assert "## External Signals" in markdown
    assert "- market change" in markdown
    assert "## Internal Signals" in markdown
    assert "- Poland" in markdown
    assert "internal-retrospective.txt" in markdown
    assert "What changes next quarter?" in markdown


def test_box_ai_file_ids_include_report_and_unique_internal_files() -> None:
    request = BoxAIReviewRequest(
        report_file_id="100",
        report_text="External research report.",
        internal_file_ids=["200", "300", "200"],
        research_question="Compare external and internal evidence.",
    )

    assert _box_ai_file_ids(request) == ["100", "200", "300"]


def test_box_ai_hub_request_uses_the_hub_as_its_only_item() -> None:
    request = BoxAIReviewRequest(
        report_file_id="100",
        report_text="External research report with cited public evidence.",
        internal_hub_id="900",
        research_question="Compare external and internal evidence.",
    )

    mode, prompt, items = _box_ai_request(request)

    assert mode == CreateAiAskMode.SINGLE_ITEM_QA
    assert [(item.id, item.type) for item in items] == [("900", AiItemAskTypeField.HUBS)]
    assert "External research report with cited public evidence." in prompt
    assert "curated internal Box Hub" in prompt

    _, bounded_prompt, _ = _box_ai_request(
        request.model_copy(
            update={
                "report_text": "report " * 3_000,
                "research_question": "question " * 2_000,
            }
        )
    )
    assert len(bounded_prompt) <= 10_000
    assert "Context shortened to fit the Box AI prompt limit." in bounded_prompt


def test_box_ai_file_request_includes_report_and_internal_files() -> None:
    request = BoxAIReviewRequest(
        report_file_id="100",
        report_text="External research report.",
        internal_file_ids=["200", "300"],
        research_question="Compare external and internal evidence.",
    )

    mode, _, items = _box_ai_request(request)

    assert mode == CreateAiAskMode.MULTIPLE_ITEM_QA
    assert [(item.id, item.type) for item in items] == [
        ("100", AiItemAskTypeField.FILE),
        ("200", AiItemAskTypeField.FILE),
        ("300", AiItemAskTypeField.FILE),
    ]


@pytest.mark.parametrize(
    ("internal_file_ids", "internal_hub_id"),
    [
        ([], None),
        (["200"], "900"),
    ],
)
def test_box_ai_review_requires_exactly_one_internal_context_source(
    internal_file_ids: list[str],
    internal_hub_id: str | None,
) -> None:
    with pytest.raises(ValueError, match="exactly one internal Box context source"):
        BoxAIReviewRequest(
            report_file_id="100",
            report_text="External research report.",
            internal_file_ids=internal_file_ids,
            internal_hub_id=internal_hub_id,
            research_question="Compare external and internal evidence.",
        )
