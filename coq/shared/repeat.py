from typing import Optional

from .types import Edit, RangeEdit, SnippetEdit, SnippetRangeEdit


def sanitize(edit: Edit) -> Optional[Edit]:
    if isinstance(edit, SnippetRangeEdit):
        if not edit.fallback or edit.fallback == edit.new_text:
            return SnippetEdit(grammar=edit.grammar, new_text=edit.new_text)
        else:
            return Edit(new_text=edit.fallback)
    elif isinstance(edit, SnippetEdit):
        return edit
    elif isinstance(edit, RangeEdit):
        return None
    else:
        return Edit(new_text=edit.new_text)
