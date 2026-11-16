from django import template
from django.utils.safestring import mark_safe

from apps.core.markdown import render

register = template.Library()


@register.filter
def markdown(text):
    return mark_safe(render(text))


@register.filter
def duration(seconds):
    seconds = int(seconds or 0)
    h, m = divmod(seconds // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"
