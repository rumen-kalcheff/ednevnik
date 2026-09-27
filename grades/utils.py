from .models import Grade


# Периоди за статистика по вид оценки: (ключ, етикет, видове оценки)
GRADE_PERIODS = [
    ('current', 'Текущи', ['oral', 'written', 'current']),
    ('term', 'Срочни', ['term1', 'term2']),
    ('annual', 'Годишни', ['annual']),
]
_PERIOD_TYPES = {key: types for key, _label, types in GRADE_PERIODS}


def resolve_period(request):
    """Връща (period_key, grade_types) според GET параметъра ?period=.

    По подразбиране 'current' (текущи оценки: устни, контролни, текущи).
    """
    period = request.GET.get('period', 'current')
    if period not in _PERIOD_TYPES:
        period = 'current'
    return period, _PERIOD_TYPES[period]


def group_grades_by_subject(grades):
    """Групира оценки на един ученик по предмет."""

    by_subject = {}
    for g in grades:
        entry = by_subject.setdefault(g.subject_id, {
            'subject': g.subject, 'grades': [], 'finals': {}, '_teachers': set(),
        })
        entry['_teachers'].add(g.teacher.get_full_name())
        if g.grade_type in Grade.FINAL_TYPES:
            entry['finals'][g.grade_type] = g
        else:
            entry['grades'].append(g)

    sections = []
    for entry in by_subject.values():
        entry['grades'].sort(key=lambda x: x.pk)
        entry['teacher_names'] = ', '.join(sorted(entry.pop('_teachers')))
        sections.append(entry)
    sections.sort(key=lambda e: e['subject'].name)
    return sections
