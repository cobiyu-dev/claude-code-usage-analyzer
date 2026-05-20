"""도구 이름 → 기능 그룹 매핑. 사용자 config 의 tool_function_mapping 사용."""
from __future__ import annotations


def map_tool_to_function_group(
    tool_name: str,
    user_mapping: dict[str, str],
    function_groups: dict[str, dict],
) -> str:
    """
    1. user_mapping 에 있으면 그대로
    2. example_tools 기반 휴리스틱 매칭
    3. 둘 다 실패하면 'other'
    """
    if not tool_name:
        return "other"
    if tool_name in user_mapping:
        return user_mapping[tool_name]

    # 휴리스틱: 도구 이름이 example_tools 중 하나를 포함하면 매칭
    low = tool_name.lower()
    for group_name, meta in function_groups.items():
        examples = meta.get("example_tools") or []
        for ex in examples:
            if not ex:
                continue
            if str(ex).lower() in low:
                return group_name
    return "other"
