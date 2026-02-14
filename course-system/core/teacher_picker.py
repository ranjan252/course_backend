"""
Teacher style picker.

Selects the tonal variant (common/experiential/funny) for content delivery.

Phase 0: style comes from student_state.teacher_style (set during warmup).
Phase 1+: emotion system integration will make this dynamic per-session.
"""
import logging
from config.settings import DEFAULT_TEACHER_STYLE, TEACHER_STYLES

logger = logging.getLogger(__name__)


def get_style(state: dict) -> str:
    """Get teacher style from student state."""
    style = state.get("teacher_style", DEFAULT_TEACHER_STYLE)
    if style not in TEACHER_STYLES:
        logger.warning(f"Unknown teacher style '{style}', using default")
        return DEFAULT_TEACHER_STYLE
    return style


def apply_style(content: dict, style: str) -> dict:
    """
    Extract the styled variant from a content block.

    Foundation content has structure:
    {
        "parts": [{
            "content": {
                "common": { "blocks": [...] },
                "experiential": { "blocks": [...] },
                "funny": { "blocks": [...] }
            }
        }]
    }

    Returns the content with only the selected style's blocks,
    plus the "common" blocks always included.
    """
    if "parts" not in content:
        return content

    styled_parts = []
    for part in content["parts"]:
        styled_part = {k: v for k, v in part.items() if k != "content"}

        part_content = part.get("content", {})
        blocks = []

        # Common blocks always included
        common = part_content.get("common", {})
        if common.get("blocks"):
            blocks.extend(common["blocks"])

        # Add styled blocks if style is not "common"
        if style != "common" and style in part_content:
            styled = part_content[style]
            if styled.get("blocks"):
                blocks.extend(styled["blocks"])

        styled_part["blocks"] = blocks
        styled_part["questions"] = part.get("questions", [])
        styled_parts.append(styled_part)

    result = {k: v for k, v in content.items() if k != "parts"}
    result["parts"] = styled_parts
    return result