"""사람 이름 자동 발견. config/people_name_patterns.yaml 기반."""
from __future__ import annotations

import re
from collections import Counter, defaultdict


def discover_candidates(texts: list[str], people_patterns_yaml: dict) -> list[tuple[str, int]]:
    """
    texts 안에서 자동 발견 후보를 (name, count) 리스트로 반환.
    min_frequency 필터링 + 변형 묶기(deduplication) 적용.
    """
    blocks = people_patterns_yaml.get("people_name_patterns") or []
    min_freq = int(people_patterns_yaml.get("min_frequency", 3))
    dedup = bool(people_patterns_yaml.get("deduplication", True))

    candidates: Counter[str] = Counter()
    variants: dict[str, set[str]] = defaultdict(set)  # base -> {variants}

    big_text = "\n".join(t for t in texts if t)

    for block in blocks:
        name_re = block.get("name_regex")
        if not name_re:
            continue
        suf_list = block.get("suffixes") or []
        pre_list = block.get("prefixes") or []
        tag_re = block.get("tag_regex")

        # name + suffix
        for suf in suf_list:
            pat = re.compile(rf'({name_re}){re.escape(str(suf))}')
            for m in pat.finditer(big_text):
                full = m.group(0)
                base = m.group(1)
                candidates[full] += 1
                variants[base].add(full)

        # prefix + name
        for pre in pre_list:
            pat = re.compile(rf'{re.escape(str(pre))}\s*({name_re})')
            for m in pat.finditer(big_text):
                full = m.group(0)
                base = m.group(1)
                candidates[full] += 1
                variants[base].add(full)

        # @태그
        if tag_re:
            try:
                pat = re.compile(tag_re)
                for m in pat.finditer(big_text):
                    full = m.group(0)
                    candidates[full] += 1
            except re.error:
                pass

    if not candidates:
        return []

    if dedup:
        # base 별로 합산해서 대표 후보 1개로
        merged: Counter[str] = Counter()
        for base, vs in variants.items():
            total = sum(candidates[v] for v in vs)
            # 대표는 가장 흔한 변형
            rep = max(vs, key=lambda v: candidates[v])
            merged[rep] += total
        # 변형 묶기 안된 항목(태그 등)도 더하기
        used = set().union(*variants.values()) if variants else set()
        for k, v in candidates.items():
            if k not in used:
                merged[k] += v
        candidates = merged

    return [(name, c) for name, c in candidates.most_common() if c >= min_freq]
