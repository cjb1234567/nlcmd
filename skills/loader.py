import os
from typing import List, Dict, Optional, Tuple

def skills_root() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")

def list_skill_dirs() -> List[str]:
    root = skills_root()
    if not os.path.isdir(root):
        return []
    return [os.path.join(root, d) for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]

def read_skill_md(path: str) -> Tuple[Dict, str]:
    md_path = os.path.join(path, "SKILL.md")
    if not os.path.isfile(md_path):
        return {}, ""
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    meta, body = parse_frontmatter(text)
    return meta, body

def parse_frontmatter(text: str) -> Tuple[Dict, str]:
    lines = text.splitlines()
    meta: Dict = {}
    body_start = 0
    if lines and lines[0].strip() == "---":
        idx = 1
        while idx < len(lines):
            line = lines[idx]
            if line.strip() == "---":
                body_start = idx + 1
                break
            if ":" in line:
                k, v = line.split(":", 1)
                key = k.strip()
                val = v.strip()
                # simple list handling for triggers
                if key == "triggers":
                    # next lines until blank or new key
                    lst = []
                    j = idx + 1
                    while j < len(lines):
                        ln = lines[j].strip()
                        if not ln or ":" in ln or ln == "---":
                            break
                        if ln.startswith("- "):
                            lst.append(ln[2:].strip())
                        else:
                            break
                        j += 1
                    meta[key] = lst
                    idx = j - 1
                else:
                    meta[key] = val
            idx += 1
    else:
        body_start = 0
    body = "\n".join(lines[body_start:]) if body_start < len(lines) else ""
    return meta, body

def load_skill_index() -> List[Dict]:
    items: List[Dict] = []
    for d in list_skill_dirs():
        meta, body = read_skill_md(d)
        name = meta.get("name")
        desc = meta.get("description")
        if not name or not desc:
            continue
        items.append({
            "name": name,
            "description": desc,
            "triggers": meta.get("triggers", []),
            "path": d,
            "body": body
        })
    return items

def find_relevant_skills(query: str, skills: List[Dict]) -> List[Dict]:
    q = (query or "").lower()
    matched = []
    for s in skills:
        # triggers first
        for t in s.get("triggers", []):
            if t and t.lower() in q:
                matched.append(s)
                break
        else:
            # fallback: description contains
            if s.get("description", "").lower() in q:
                matched.append(s)
    return matched

def prompt_for_discovery(skills: List[Dict]) -> str:
    if not skills:
        return ""
    lines = ["Available skills (discovery):"]
    for s in skills:
        lines.append(f"- {s['name']}: {s['description']}")
    return "\n".join(lines)

def prompt_for_activation(skills: List[Dict]) -> str:
    if not skills:
        return ""
    lines = ["Activated skills instructions:"]
    for s in skills:
        lines.append(f"# Skill: {s['name']}\n{s['body']}")
    return "\n\n".join(lines)

def resolve_script(name: str) -> Optional[str]:
    # locate scripts/<name>.(py|ps1|sh|bat|cmd|exe) within skill folder
    exts = [".py", ".ps1", ".sh", ".bat", ".cmd", ".exe", ""]
    for s in load_skill_index():
        if s["name"] == name:
            base = os.path.join(s["path"], "scripts", name)
            for ext in exts:
                p = base + ext
                if os.path.isfile(p):
                    return p
    # fallback: search any skill scripts for matching basename
    for s in load_skill_index():
        scripts_dir = os.path.join(s["path"], "scripts")
        if not os.path.isdir(scripts_dir):
            continue
        for fn in os.listdir(scripts_dir):
            stem, ext = os.path.splitext(fn)
            if stem == name and os.path.isfile(os.path.join(scripts_dir, fn)):
                return os.path.join(scripts_dir, fn)
    return None
