{% autoescape off %}# {{ project.name }}

**Status:** {{ project.get_status_display }}{% if project.github_repo %} · **Repo:** https://github.com/{{ project.github_repo }}{% endif %}{% if project.start_date %} · **Started:** {{ project.start_date }}{% endif %}{% if project.target_date %} · **Target:** {{ project.target_date }}{% endif %}
**Progress:** {{ project.progress }}%{% if project.live_url %} · **Live:** {{ project.live_url }}{% endif %}

{{ project.description }}

## Milestones
{% for m in project.milestones.all %}- **{{ m.title }}** — {{ m.progress }}%{% if m.due_date %} · due {{ m.due_date }}{% endif %}
{% empty %}_No milestones._
{% endfor %}
## Tasks
{% for t in project.tasks.all %}- [{% if t.status == "done" %}x{% else %} {% endif %}] {{ t.title }}{% if t.status == "doing" %} _(in progress)_{% endif %}{% if t.due_date %} — due {{ t.due_date }}{% endif %}
{% empty %}_No tasks._
{% endfor %}
## Links
{% for l in project.links.all %}- [{{ l.title }}]({{ l.url }})
{% empty %}_No links._
{% endfor %}
## Timeline
{% for u in project.updates.all %}### {{ u.created_at|date:"Y-m-d" }} — {{ u.title }}
{% if u.body %}
{{ u.body }}
{% endif %}
{% empty %}_No updates._
{% endfor %}{% if project.readme %}
## README

{{ project.readme }}
{% endif %}{% endautoescape %}
