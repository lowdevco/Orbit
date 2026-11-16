import re

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import NoteForm
from .models import Note


def _note(request, pk):
    return get_object_or_404(Note, pk=pk, owner=request.user)


def note_list(request):
    q = request.GET.get("q", "").strip()
    tag = request.GET.get("tag", "").strip()
    notes = request.user.notes.select_related("project")
    if q:
        notes = notes.filter(Q(title__icontains=q) | Q(body__icontains=q) | Q(tags__icontains=q))
    if tag:
        notes = notes.filter(tags__iregex=rf"(^|,)\s*{re.escape(tag)}\s*(,|$)")
    all_tags = sorted({t for n in request.user.notes.only("tags") for t in n.tag_list}, key=str.lower)
    return render(request, "notes/list.html", {"notes": notes, "q": q, "tag": tag, "all_tags": all_tags})


def note_create(request):
    initial = {}
    if request.GET.get("project"):
        initial["project"] = request.user.projects.filter(slug=request.GET["project"]).first()
    form = NoteForm(request.POST or None, user=request.user, initial=initial)
    if form.is_valid():
        note = form.save(commit=False)
        note.owner = request.user
        note.save()
        return redirect(note)
    return render(request, "notes/form.html", {"form": form})


def note_detail(request, pk):
    return render(request, "notes/detail.html", {"note": _note(request, pk)})


def note_edit(request, pk):
    note = _note(request, pk)
    form = NoteForm(request.POST or None, instance=note, user=request.user)
    if form.is_valid():
        form.save()
        return redirect(note)
    return render(request, "notes/form.html", {"form": form, "note": note})


@require_POST
def note_delete(request, pk):
    _note(request, pk).delete()
    messages.success(request, "Note deleted.")
    return redirect("notes:list")


@require_POST
def note_pin(request, pk):
    note = _note(request, pk)
    note.pinned = not note.pinned
    note.save(update_fields=["pinned"])
    return redirect("notes:list" if request.POST.get("next") == "list" else note)


def note_export(request, pk):
    note = _note(request, pk)
    text = f"# {note.title}\n\n{note.body}\n"
    resp = HttpResponse(text, content_type="text/markdown; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="note-{note.pk}.md"'
    return resp
