"""
개인 로컬 셋업 수집 — ~/.claude/ 와 ~/.claude.json 에서 다른 사람과 공유 안 하는 설정 추출.

Stage C 또는 Stage D 가 호출. 결과는 aggregated.json 의 local_setup 키로 들어가서
Stage D 가 자연어 섹션으로 풀어 쓴다.

수집 대상:
1. 개인 MCP 서버 — ~/.claude.json 의 mcpServers
2. 개인 CLAUDE.md — ~/.claude/CLAUDE.md
3. 개인 skill · plugin · slash command — ~/.claude/skills/, plugins/installed_plugins.json, commands/
4. 개인 hooks · statusline · 그 외 — ~/.claude/settings.json

시크릿/개인정보 마스킹 자동 적용.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .masker import compile_secret_patterns, mask_any


def _safe_read_json(path: Path) -> dict | None:
    try:
        with path.open() as f:
            return json.load(f)
    except Exception:
        return None


def _safe_read_text(path: Path) -> str | None:
    try:
        with path.open() as f:
            return f.read()
    except Exception:
        return None


def _mask_home_path(s: str, home: Path) -> str:
    return s.replace(str(home), "~")


def extract_mcp_servers(claude_json_path: Path, compiled_secrets: list) -> list[dict]:
    """~/.claude.json 의 mcpServers 추출. 값은 시크릿 마스킹."""
    data = _safe_read_json(claude_json_path) or {}
    servers = data.get("mcpServers") or {}
    out = []
    for name, conf in servers.items():
        if not isinstance(conf, dict):
            continue
        entry = {
            "name": name,
            "type": conf.get("type"),  # stdio / sse / http
            "command": conf.get("command"),
        }
        # args 에 path/url 만 보존, 시크릿 마스킹
        if conf.get("args"):
            entry["args_summary"] = mask_any(conf.get("args"), compiled_secrets)
        # env 키만 노출, 값은 마스킹
        env = conf.get("env") or {}
        if env:
            entry["env_keys"] = sorted(env.keys())
        # url 은 마스킹 적용
        if conf.get("url"):
            entry["url"] = mask_any(conf.get("url"), compiled_secrets)
        out.append(entry)
    return out


def extract_personal_claude_md(claude_md_path: Path, home: Path) -> dict | None:
    """~/.claude/CLAUDE.md 의 핵심 섹션 헤더와 길이만 (전문 노출 X)."""
    text = _safe_read_text(claude_md_path)
    if not text:
        return None
    headers = re.findall(r"^(#{1,3})\s+(.+)$", text, re.MULTILINE)
    return {
        "exists": True,
        "char_count": len(text),
        "section_headers": [h[1] for h in headers[:20]],
    }


def extract_plugins(plugins_json_path: Path) -> list[dict]:
    """installed_plugins.json 에서 설치된 플러그인 목록."""
    data = _safe_read_json(plugins_json_path) or {}
    plugins = data.get("plugins") or {}
    out = []
    for full_name, instances in plugins.items():
        if not isinstance(instances, list) or not instances:
            continue
        inst = instances[0]
        # full_name 예: "claude-code-setup@claude-plugins-official"
        name = full_name.split("@")[0]
        marketplace = full_name.split("@")[1] if "@" in full_name else None
        out.append({
            "name": name,
            "marketplace": marketplace,
            "version": inst.get("version"),
            "installed_at": inst.get("installedAt"),
            "is_company_internal": marketplace and "logistics" in marketplace.lower(),
        })
    return out


def extract_skills(skills_dir: Path) -> list[dict]:
    """~/.claude/skills/ 안의 스킬 디렉터리 이름과 SKILL.md 첫 줄 description."""
    if not skills_dir.exists() or not skills_dir.is_dir():
        return []
    out = []
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        desc = None
        if skill_md.exists():
            text = _safe_read_text(skill_md) or ""
            # frontmatter 의 description: 추출 시도
            m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
            if m:
                desc = m.group(1).strip()
        out.append({
            "name": entry.name,
            "description": desc,
        })
    return out


def extract_slash_commands(commands_dir: Path) -> list[dict]:
    """~/.claude/commands/ 의 사용자 정의 슬래시 커맨드."""
    if not commands_dir.exists() or not commands_dir.is_dir():
        return []
    out = []
    for entry in sorted(commands_dir.iterdir()):
        if entry.suffix != ".md":
            continue
        text = _safe_read_text(entry) or ""
        # 첫 줄 또는 frontmatter description
        first_line = text.split("\n")[0][:120] if text else ""
        out.append({
            "name": entry.stem,
            "first_line": first_line,
        })
    return out


def extract_settings(settings_path: Path, compiled_secrets: list, home: Path) -> dict:
    """~/.claude/settings.json 의 설정 요약. 시크릿 마스킹."""
    data = _safe_read_json(settings_path) or {}
    out: dict[str, Any] = {}

    # env: 키만 노출
    env = data.get("env") or {}
    if env:
        out["env_keys"] = sorted(env.keys())

    # permissions: allow/deny 의 갯수만
    perms = data.get("permissions") or {}
    if perms:
        out["permissions"] = {
            "allow_count": len(perms.get("allow") or []),
            "deny_count": len(perms.get("deny") or []),
            "ask_count": len(perms.get("ask") or []),
        }

    # hooks: hook event 이름만 + 갯수
    hooks = data.get("hooks") or {}
    if hooks:
        hook_summary = {}
        for event, defs in hooks.items():
            if isinstance(defs, list):
                hook_summary[event] = len(defs)
        out["hooks"] = hook_summary

    # statusLine: 명령 일부 (경로 마스킹)
    sl = data.get("statusLine") or {}
    if sl:
        cmd = sl.get("command")
        if cmd:
            cmd = _mask_home_path(cmd, home)
            cmd = mask_any(cmd, compiled_secrets)
            out["statusline"] = {"type": sl.get("type"), "command": cmd}

    # 기타 토글
    for k in ("alwaysThinkingEnabled", "effortLevel", "teammateMode",
              "skipAutoPermissionPrompt"):
        if k in data:
            out[k] = data[k]

    # enabledPlugins 키만
    ep = data.get("enabledPlugins") or {}
    if ep:
        out["enabled_plugin_keys"] = sorted(ep.keys())

    return out


def extract_all(repo_root: Path, secret_patterns_yaml: list[dict]) -> dict:
    """모두 모아서 dict 반환. aggregated.json 의 local_setup 키로 들어감."""
    home = Path.home()
    compiled = compile_secret_patterns(secret_patterns_yaml)

    return {
        "mcp_servers": extract_mcp_servers(home / ".claude.json", compiled),
        "personal_claude_md": extract_personal_claude_md(
            home / ".claude" / "CLAUDE.md", home
        ),
        "plugins": extract_plugins(
            home / ".claude" / "plugins" / "installed_plugins.json"
        ),
        "skills": extract_skills(home / ".claude" / "skills"),
        "slash_commands": extract_slash_commands(home / ".claude" / "commands"),
        "settings": extract_settings(
            home / ".claude" / "settings.json", compiled, home
        ),
    }
