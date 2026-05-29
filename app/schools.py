"""Разделение корпуса на две школы: «Летово» (основная, 7–11) и «Летово Джуниор» (началка).

В корпусе есть документы обеих школ. Без разделения вопрос вроде «какая шкала оценок» тянет
документы обеих школ и даёт противоречивые ответы. Поэтому:
- каждый документ помечается школой (`school`): "junior" | "main";
- по умолчанию отвечаем про основную школу; документы Джуниор берём только если вопрос явно
  про начальную школу/Джуниор.
"""
from __future__ import annotations

import re

_JUNIOR_DOC = re.compile(r"дж[ую]ниор|dzhunior|junior|джун", re.I)
# Запрос явно про начальную школу / Джуниор:
_JUNIOR_QUERY = re.compile(
    r"дж[ую]ниор|dzhunior|junior|начальн\w*\s+школ|началк|младш\w*\s+школ|\bНОО\b|нач\.\s*школ|"
    r"1[-–—]?4\s*класс|перв\w+\s+класс|втор\w+\s+класс|трет\w+\s+класс|четверт\w+\s+класс",
    re.I,
)
# Явное указание на основную школу (перебивает контекст про Джуниор):
_MAIN_QUERY = re.compile(
    r"обычн\w*\s+школ|основн\w*\s+школ|старш\w*\s+школ|средн\w*\s+школ|7[-–—]?11|"
    r"не\s+(?:в\s+)?дж[ую]ниор",
    re.I,
)

MAIN = "main"
JUNIOR = "junior"


def school_of(local_name: str | None, title: str | None = None) -> str:
    text = f"{local_name or ''} {title or ''}"
    return JUNIOR if _JUNIOR_DOC.search(text) else MAIN


def target_school(question: str) -> str:
    """Какую школу имеет в виду пользователь. По умолчанию — основная."""
    if _MAIN_QUERY.search(question or ""):
        return MAIN
    return JUNIOR if _JUNIOR_QUERY.search(question or "") else MAIN


def target_school_dialog(question: str, prev_user: str = "") -> str:
    """Школа с учётом диалога. Явный признак в ТЕКУЩЕМ вопросе перебивает контекст."""
    q = question or ""
    if _MAIN_QUERY.search(q):
        return MAIN
    if _JUNIOR_QUERY.search(q):
        return JUNIOR
    # текущий вопрос без признака школы — наследуем из предыдущего вопроса
    if _JUNIOR_QUERY.search(prev_user or "") and not _MAIN_QUERY.search(prev_user or ""):
        return JUNIOR
    return MAIN
