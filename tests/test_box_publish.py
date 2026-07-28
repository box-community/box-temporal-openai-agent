import pytest

from activities.box_publish import _box_ai_file_ids, format_box_ai_digest
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
        internal_file_ids=["200", "300", "200"],
        research_question="Compare external and internal evidence.",
    )

    assert _box_ai_file_ids(request) == ["100", "200", "300"]


def test_box_ai_file_ids_require_internal_context() -> None:
    request = BoxAIReviewRequest(
        report_file_id="100",
        internal_file_ids=[],
        research_question="Compare external and internal evidence.",
    )

    with pytest.raises(ValueError, match="internal Box content"):
        _box_ai_file_ids(request)
