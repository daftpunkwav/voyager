"""Notes-page UI state: get/set_notes_view.

Responsibilities:
- Validate and persist the notes-page UI state under notes.ui.* setting
  keys (mode, layout, list state, sort, filter, panel, density, widths)
- Emit notes.ui.changed on updates so all viewers stay in sync

Separate from the site-wide appearance settings; user buttons and agents
have equal access to the same capability.
"""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ActorRef, DomainEvent, ErrorSuffix, Event, ServiceError

from .runtime import ACTOR, DOMAIN, get_any, registry, require_deps

_UI_FONT_MIN, _UI_FONT_MAX, _UI_FONT_DEFAULT = 12, 24, 15
_UI_TOC_WIDTH_MIN, _UI_TOC_WIDTH_MAX, _UI_TOC_WIDTH_DEFAULT = 148, 480, 188
_UI_MODES = ("edit", "preview", "split")
_UI_LAYOUTS = ("list", "card")
_UI_LIST_STATES = ("active", "archived")
_UI_SORTS = ("updated", "created", "title")
_UI_FILTERS = ("all", "pinned", "untitled", "unlinked", "today")
_UI_PANELS = ("none", "trash")
_UI_DENSITIES = ("comfortable", "compact")
_UI_QUERY_MAX = 80
_UI_SOURCE_MAX = 80
_UI_QUOTE_MAX = 500
_UI_KEYS = {
    "font_size": "notes.ui.font_size",
    "mode": "notes.ui.mode",
    "layout": "notes.ui.layout",
    "sync_scroll": "notes.ui.sync_scroll",
    "list_state": "notes.ui.list_state",
    "sort": "notes.ui.sort",
    "filter": "notes.ui.filter",
    "query": "notes.ui.query",
    "source_id": "notes.ui.source_id",
    "panel": "notes.ui.panel",
    "density": "notes.ui.density",
    "toc_width": "notes.ui.toc_width",
}


def _ui_get(key: str, default):
    s = require_deps().settings
    if s is None:
        return default
    try:
        val = s.get(key)
    except ServiceError:
        return default
    return default if val is None else val


def _clamp_toc_width(raw: object) -> int:
    if not isinstance(raw, (int, float, str)):
        return _UI_TOC_WIDTH_DEFAULT
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return _UI_TOC_WIDTH_DEFAULT
    return max(_UI_TOC_WIDTH_MIN, min(_UI_TOC_WIDTH_MAX, n))


def _read_notes_view() -> dict:
    mode = str(_ui_get("notes.ui.mode", "edit"))
    layout = str(_ui_get("notes.ui.layout", "list"))
    list_state = str(_ui_get("notes.ui.list_state", "active"))
    sort = str(_ui_get("notes.ui.sort", "updated"))
    filt = str(_ui_get("notes.ui.filter", "all"))
    panel = str(_ui_get("notes.ui.panel", "none"))
    density = str(_ui_get("notes.ui.density", "comfortable"))
    return {
        "font_size": int(_ui_get("notes.ui.font_size", _UI_FONT_DEFAULT)),
        "mode": mode if mode in _UI_MODES else "edit",
        "layout": layout if layout in _UI_LAYOUTS else "list",
        "sync_scroll": bool(_ui_get("notes.ui.sync_scroll", True)),
        "list_state": list_state if list_state in _UI_LIST_STATES else "active",
        "sort": sort if sort in _UI_SORTS else "updated",
        "filter": filt if filt in _UI_FILTERS else "all",
        "query": str(_ui_get("notes.ui.query", "") or "")[:_UI_QUERY_MAX],
        "source_id": str(_ui_get("notes.ui.source_id", "") or "")[:_UI_SOURCE_MAX],
        "panel": panel if panel in _UI_PANELS else "none",
        "density": density if density in _UI_DENSITIES else "comfortable",
        "toc_width": _clamp_toc_width(_ui_get("notes.ui.toc_width", _UI_TOC_WIDTH_DEFAULT)),
        "persisted": require_deps().settings is not None,
    }


async def _emit_notes_ui(payload: dict, actor: ActorRef) -> None:
    deps = require_deps()
    if deps.bus is not None:
        await deps.bus.publish(
            Event(type=DomainEvent.NOTES_UI_CHANGED, actor=actor, payload=payload)
        )


#: Enum parameters -> whitelists, driving table-based validation in set_notes_view.
_VIEW_ENUM_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mode", _UI_MODES),
    ("layout", _UI_LAYOUTS),
    ("list_state", _UI_LIST_STATES),
    ("sort", _UI_SORTS),
    ("filter", _UI_FILTERS),
    ("panel", _UI_PANELS),
    ("density", _UI_DENSITIES),
)


def _normalize_view_args(args: dict) -> dict:
    """Validate and normalize UI arguments; invalid values raise INVALID_INPUT.

    Returns a normalized copy of the arguments (source_id truncated and
    stripped of traversal characters, query truncated) for direct
    consumption by the patch builder.
    """
    for name, allowed in _VIEW_ENUM_RULES:
        value = args.get(name)
        if value is not None and value not in allowed:
            raise ServiceError(
                DOMAIN, ErrorSuffix.INVALID_INPUT, f"{name} must be one of {list(allowed)}"
            )
    font_size = args.get("font_size")
    if font_size is not None and not (_UI_FONT_MIN <= int(font_size) <= _UI_FONT_MAX):
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"font_size must be within {_UI_FONT_MIN}–{_UI_FONT_MAX}",
        )
    out = dict(args)
    if out.get("source_id") is not None:
        sid = str(out["source_id"]).strip()
        if "/" in sid or "\\" in sid or ".." in sid:
            raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "Invalid source_id")
        out["source_id"] = sid[:_UI_SOURCE_MAX]
    if out.get("query") is not None:
        out["query"] = str(out["query"])[:_UI_QUERY_MAX]
    return out


def _view_patch(args: dict, font_delta: int | None, toc_width: int | None, view: dict) -> dict:
    """Build the persistence patch from normalized arguments.

    font_delta is applied relative to the current font size and clamped;
    toc_width is clamped too. The panel fallback (note_id -> none) stays
    with the caller.
    """
    patch: dict = {}
    if args.get("font_size") is not None:
        patch["font_size"] = int(args["font_size"])
    elif font_delta is not None:
        nxt = int(view["font_size"]) + int(font_delta)
        patch["font_size"] = max(_UI_FONT_MIN, min(_UI_FONT_MAX, nxt))
    if args.get("sync_scroll") is not None:
        patch["sync_scroll"] = bool(args["sync_scroll"])
    for name in ("mode", "layout", "list_state", "sort", "filter", "query", "source_id", "density"):
        if args.get(name) is not None:
            patch[name] = args[name]
    if toc_width is not None:
        patch["toc_width"] = _clamp_toc_width(toc_width)
    if args.get("panel") is not None:
        patch["panel"] = args["panel"]
    return patch


@capability(
    registry,
    name="get_notes_view",
    description="Read the notes-page UI: font size/view/layout/active-or-archived/sort/filter/keyword/"
    "linked source/trash panel/density/TOC width. Independent of the site-wide font.",
)
def get_notes_view() -> dict:
    return _read_notes_view()


@capability(
    registry,
    name="set_notes_view",
    description="Update the notes-page UI (user buttons and agents invoke this capability equivalently; does not affect the whole site)."
    " font_size or font_delta; mode=edit|preview|split;"
    "layout=list|card;sync_scroll;list_state=active|archived;"
    "sort=updated|created|title;filter=all|pinned|untitled|unlinked|today;"
    "query keyword;source_id linked source (empty=all);"
    "panel=none|trash;density=comfortable|compact;"
    "toc_width TOC width (pixels, 148–480);"
    "assist=true opens the notes-page floating chat; quote hands the selection to the scout persona for a quick read (not persisted);"
    "note_id opens a note (including new); index=true returns to the list.",
    cost=1,
)
async def set_notes_view(
    font_size: int | None = None,
    font_delta: int | None = None,
    mode: str | None = None,
    layout: str | None = None,
    sync_scroll: bool | None = None,
    list_state: str | None = None,
    sort: str | None = None,
    filter: str | None = None,
    query: str | None = None,
    source_id: str | None = None,
    panel: str | None = None,
    density: str | None = None,
    toc_width: int | None = None,
    assist: bool = False,
    quote: str | None = None,
    note_id: str | None = None,
    index: bool = False,
    _actor: ActorRef | None = None,
) -> dict:
    # The 18 parameters are the REST contract; validation and patch building
    # are delegated to the table-driven helpers.
    quote_text = None
    if quote is not None:
        quote_text = " ".join(str(quote).split())[:_UI_QUOTE_MAX] or None
    args = _normalize_view_args(
        {
            "font_size": font_size,
            "mode": mode,
            "layout": layout,
            "sync_scroll": sync_scroll,
            "list_state": list_state,
            "sort": sort,
            "filter": filter,
            "query": query,
            "source_id": source_id,
            "panel": panel,
            "density": density,
        }
    )
    touched = (
        any(
            v is not None
            for v in (
                args["font_size"],
                font_delta,
                args["mode"],
                args["layout"],
                args["sync_scroll"],
                args["list_state"],
                note_id,
                args["sort"],
                args["filter"],
                args["query"],
                args["source_id"],
                args["panel"],
                args["density"],
                toc_width,
            )
        )
        or index
        or assist
        or quote_text is not None
    )
    if not touched:
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "Provide at least one UI parameter",
            hint="font_size / font_delta / mode / layout / "
            "sync_scroll / list_state / sort / filter / "
            "query / source_id / panel / density / toc_width / "
            "assist / quote / note_id / index",
        )
    if note_id and note_id != "new" and not index:
        get_any(note_id)

    view = _read_notes_view()
    patch = _view_patch(args, font_delta, toc_width, view)
    if args["panel"] is None and note_id:
        patch["panel"] = "none"

    actor = _actor or ACTOR
    deps = require_deps()
    persisted = deps.settings is not None
    if patch and deps.settings is not None:
        for field, value in patch.items():
            await deps.settings.set(_UI_KEYS[field], value, actor)
        view = _read_notes_view()
    else:
        view = {**view, **patch, "persisted": persisted}

    action = "index" if index else ("open" if note_id else None)
    out = {
        **view,
        "persisted": persisted,
        "action": action,
        "note_id": None if index else note_id,
        "assist": bool(assist) or bool(quote_text),
        "quote": quote_text or "",
    }
    event_payload = {
        **patch,
        "action": action,
        "note_id": out["note_id"],
        "persisted": persisted,
    }
    if assist:
        event_payload["assist"] = True
    if quote_text:
        event_payload["quote"] = quote_text
        event_payload["assist"] = True
    await _emit_notes_ui(event_payload, actor)
    return out
