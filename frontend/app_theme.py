import importlib


def get_theme(name="dark"):

    import frontend.styles._colors as _colors
    import frontend.styles.theme_parts as _theme_parts

    importlib.reload(_colors)
    _theme_parts = importlib.reload(_theme_parts)

    return _theme_parts.build_dark_theme() + _theme_parts.build_sidebar_dark()


def _current_text_pri() -> str:
    import frontend.styles._colors as _colors

    return str(getattr(_colors, "_TEXT_PRI", "#e6edf3"))


def safe_set_point_size(qfont, size, default=12):
    try:
        s = int(size)
    except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
        s = default
    if s <= 0:
        s = default
    qfont.setPointSize(s)


def page_base_styles(font_size: int = 13) -> str:
    text_pri = _current_text_pri()
    return f"""
    QWidget {{
        color: {text_pri};
        font-family: 'Segoe UI Variable', 'Segoe UI', 'Bahnschrift', 'Tahoma', sans-serif;
        font-size: {font_size}px;
        background-color: transparent;
    }}
    QLabel {{
        background: transparent;
    }}
    """


THEME_REGISTRY = {
    "page_base": page_base_styles(),
}

