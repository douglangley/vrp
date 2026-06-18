"""HTML rendering for the accessible webview.

VRP does not run a web server. Instead it renders HTML *strings* with Jinja2
and hands them to ``AccessibleWebView.set_content`` / ``.append``. The webview
wraps the fragment in a full document (with its own ``lang`` and styles), so
templates here produce body fragments, not whole pages.

Because there is no HTTP server, external ``<link>``/``<script>`` references
won't load inside the webview document. Assets that a fragment needs are
inlined via :func:`read_static`. ``base_dir`` resolution also works in a frozen
Nuitka build, where ``static`` and ``templates`` are bundled next to the exe.
"""

from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def _base_dir() -> Path:
    """Directory that contains the ``templates`` and ``static`` folders.

    In development this is the project root (the parent of this package). In a
    frozen build the data dirs sit beside the executable, so fall back to the
    executable's directory when the package-relative path is absent.
    """
    pkg_parent = Path(__file__).resolve().parent.parent
    if (pkg_parent / "templates").is_dir():
        return pkg_parent
    return Path(sys.argv[0]).resolve().parent


BASE_DIR = _base_dir()
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


# GPLv3 / good-citizen requirement (see CLAUDE.md): the CHIRP attribution must
# appear on every view. Appended centrally by render_view so no template can
# omit it. The exact wording is mandated and must not be changed or obscured.
ATTRIBUTION_HTML = (
    '<footer>'
    '<p>Radio driver support provided by the '
    '<a href="https://chirpmyradio.com">CHIRP project — chirpmyradio.com</a>.</p>'
    '</footer>'
)


def render(template_name: str, **context) -> str:
    """Render a Jinja2 template from ``templates/`` to an HTML string."""
    return _env.get_template(template_name).render(**context)


def render_view(template_name: str, **context) -> str:
    """Render a full view fragment for ``set_content``: template + attribution.

    Use this (not :func:`render`) for anything shown as a top-level view, so the
    mandatory CHIRP attribution footer is always present.
    """
    return render(template_name, **context) + ATTRIBUTION_HTML


def render_macro(template_name: str, macro_name: str, *args) -> str:
    """Render a single Jinja macro to a string.

    Used to re-render one channel row (the same macro the full table uses) for
    surgical, single-row DOM updates after an edit.
    """
    macro = getattr(_env.get_template(template_name).module, macro_name)
    return str(macro(*args))


def read_static(relative_path: str) -> str:
    """Read a file from ``static/`` as text, for inlining into a fragment."""
    return (STATIC_DIR / relative_path).read_text(encoding="utf-8")
