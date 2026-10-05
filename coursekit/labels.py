"""User-facing interface strings.

Every course picks a base language with `language:` in course.yml and can override any
individual string with `labels:`. Strings may contain `{n}` (or `{h}`/`{m}`) placeholders.
"""

from __future__ import annotations

from typing import Dict

LABELS: Dict[str, Dict[str, str]] = {
    "en": {
        "skip_to_content": "Skip to content",
        "toggle_sidebar": "Show or hide the chapter list",
        "toggle_theme": "Switch between light and dark mode",
        "home": "Home",
        "about": "About this course",
        "last_updated": "Last updated",
        "written_by": "Written by",
        "duration": "Duration",
        "chapters": "Chapters",
        "chapters_count": "{n} chapters",
        "part": "Part {n}",
        "chapter": "Chapter {n}",
        "minutes": "{n} min",
        "hours_minutes": "{h} h {m} min",
        "remaining": "{t} remaining",
        "back": "Back",
        "next": "Next",
        "finish": "Finish",
        "copy": "Copy",
        "copied": "Copied",
        "copy_code": "Copy code to clipboard",
        "edit": "Edit this chapter",
        "reset_progress": "Reset progress",
        "reset_confirm": "Reset your progress in this course?",
        "course_complete": "You finished the course — nice work!",
        "progress": "Course progress",
        "link_to_section": "Link to this section",
        "close": "Close",
        "quiz": "Quick check",
        "quiz_multi": "Select all that apply",
        "quiz_correct": "Correct!",
        "quiz_incorrect": "Not quite — try again.",
        "quiz_check": "Check answer",
        "quiz_reveal": "Show answer",
        "note": "Note",
        "info": "Info",
        "tip": "Tip",
        "success": "Success",
        "important": "Important",
        "warning": "Warning",
        "caution": "Caution",
        "danger": "Danger",
        "exercise": "Exercise",
        "details": "Details",
        "hint": "Hint",
        "solution": "Show solution",
    },
    "pt": {
        "skip_to_content": "Pular para o conteúdo",
        "toggle_sidebar": "Mostrar ou ocultar a lista de capítulos",
        "toggle_theme": "Alternar entre modo claro e escuro",
        "home": "Início",
        "about": "Sobre este curso",
        "last_updated": "Última atualização",
        "written_by": "Escrito por",
        "duration": "Duração",
        "chapters": "Capítulos",
        "chapters_count": "{n} capítulos",
        "part": "Parte {n}",
        "chapter": "Capítulo {n}",
        "minutes": "{n} min",
        "hours_minutes": "{h} h {m} min",
        "remaining": "{t} restantes",
        "back": "Voltar",
        "next": "Avançar",
        "finish": "Concluir",
        "copy": "Copiar",
        "copied": "Copiado",
        "copy_code": "Copiar código",
        "edit": "Editar este capítulo",
        "reset_progress": "Reiniciar progresso",
        "reset_confirm": "Reiniciar seu progresso neste curso?",
        "course_complete": "Você concluiu o curso — parabéns!",
        "progress": "Progresso do curso",
        "link_to_section": "Link para esta seção",
        "close": "Fechar",
        "quiz": "Teste rápido",
        "quiz_multi": "Selecione todas as corretas",
        "quiz_correct": "Correto!",
        "quiz_incorrect": "Ainda não — tente novamente.",
        "quiz_check": "Verificar resposta",
        "quiz_reveal": "Mostrar resposta",
        "note": "Nota",
        "info": "Informação",
        "tip": "Dica",
        "success": "Sucesso",
        "important": "Importante",
        "warning": "Atenção",
        "caution": "Cuidado",
        "danger": "Perigo",
        "exercise": "Exercício",
        "details": "Detalhes",
        "hint": "Dica",
        "solution": "Mostrar solução",
    },
    "es": {
        "skip_to_content": "Saltar al contenido",
        "toggle_sidebar": "Mostrar u ocultar la lista de capítulos",
        "toggle_theme": "Cambiar entre modo claro y oscuro",
        "home": "Inicio",
        "about": "Acerca de este curso",
        "last_updated": "Última actualización",
        "written_by": "Escrito por",
        "duration": "Duración",
        "chapters": "Capítulos",
        "chapters_count": "{n} capítulos",
        "part": "Parte {n}",
        "chapter": "Capítulo {n}",
        "minutes": "{n} min",
        "hours_minutes": "{h} h {m} min",
        "remaining": "quedan {t}",
        "back": "Atrás",
        "next": "Siguiente",
        "finish": "Terminar",
        "copy": "Copiar",
        "copied": "Copiado",
        "copy_code": "Copiar código",
        "edit": "Editar este capítulo",
        "reset_progress": "Reiniciar progreso",
        "reset_confirm": "¿Reiniciar tu progreso en este curso?",
        "course_complete": "Terminaste el curso — ¡buen trabajo!",
        "progress": "Progreso del curso",
        "link_to_section": "Enlace a esta sección",
        "close": "Cerrar",
        "quiz": "Comprobación rápida",
        "quiz_multi": "Selecciona todas las correctas",
        "quiz_correct": "¡Correcto!",
        "quiz_incorrect": "Todavía no — inténtalo de nuevo.",
        "quiz_check": "Comprobar respuesta",
        "quiz_reveal": "Mostrar respuesta",
        "note": "Nota",
        "info": "Información",
        "tip": "Consejo",
        "success": "Éxito",
        "important": "Importante",
        "warning": "Advertencia",
        "caution": "Precaución",
        "danger": "Peligro",
        "exercise": "Ejercicio",
        "details": "Detalles",
        "hint": "Pista",
        "solution": "Mostrar solución",
    },
}

# Strings the browser runtime needs (the rest are only used at build time).
RUNTIME_KEYS = (
    "minutes", "hours_minutes", "remaining", "back", "next", "finish", "copy", "copied",
    "reset_confirm", "course_complete", "close", "quiz_multi", "quiz_correct",
    "quiz_incorrect", "quiz_check", "quiz_reveal",
)


def resolve_labels(language: str, overrides: Dict[str, str] | None = None) -> Dict[str, str]:
    """English defaults, then the base language (`pt-BR` falls back to `pt`), then overrides."""
    base = (language or "en").lower()
    labels = dict(LABELS["en"])
    labels.update(LABELS.get(base, LABELS.get(base.split("-")[0], {})))
    for key, value in (overrides or {}).items():
        labels[str(key)] = str(value)
    return labels


def format_minutes(total: int, labels: Dict[str, str]) -> str:
    if total >= 60:
        return labels["hours_minutes"].format(h=total // 60, m=total % 60)
    return labels["minutes"].format(n=total)
