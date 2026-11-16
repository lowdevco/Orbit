import markdown as md
import nh3


def render(text):
    """Markdown -> sanitized HTML. Sanitizing matters: notes and READMEs are shown on public share pages."""
    html = md.markdown(text or "", extensions=["fenced_code", "tables", "sane_lists"])
    return nh3.clean(html)
