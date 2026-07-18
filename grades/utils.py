from .models import Grade


def group_grades_by_subject(grades):
    """Групира оценки на един ученик по предмет.

    Връща списък от секции, подредени по име на предмет:
        [{'subject', 'teacher_names', 'grades' (текущи, по реда на добавяне),
          'finals' {grade_type: Grade}}]
    `grades` трябва да е iterable от Grade със select_related('subject', 'teacher').
    """
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
