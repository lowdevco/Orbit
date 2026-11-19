import re

import markdown as md
import nh3

LIST_ITEM = re.compile(r"\s*([-*+]|\d+[.)])\s")


def _gfm_lists(text):
    """Insert the blank line Python-Markdown needs before a list, so lists work GitHub-style without one."""
    out, prev, fenced = [], "", False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        if not fenced and LIST_ITEM.match(line) and prev.strip() and not LIST_ITEM.match(prev):
            out.append("")
        out.append(line)
        prev = "" if fenced else line
    return "\n".join(out)


def render(text):
    """Markdown -> sanitized HTML. Sanitizing matters: notes and READMEs are shown on public share pages."""
    # nl2br keeps single line breaks, so the preview matches what was typed.
    html = md.markdown(_gfm_lists(text or ""), extensions=["fenced_code", "tables", "sane_lists", "nl2br"])
    return nh3.clean(html)
