"""Shared TUI theme — spacing and structure, applied app-wide.

Kept separate from per-screen layout so every current and future screen gets a
consistent, uncramped look without repeating CSS. This is the *foundation*
(breathing room, consistent insets, contained tables); deep visual polish
(colour palette, branding) comes later, once all screens exist.

Loaded via ``WiseQLApp.CSS`` so it cascades to all pushed screens. Tests assert
on data and behaviour, never layout, so changes here are risk-free.
"""

THEME = """
/* Tables: inset from the screen edges and visually contained, so rows never
   sit flush against the terminal border. */
DataTable {
    margin: 1 2;
    border: round $primary 40%;
}

/* Status / summary / hint lines above a table: matching horizontal inset and a
   little space below the header. */
#run-status, #conn-hint, #detail-summary, #result-status {
    padding: 1 2 0 2;
}

/* Modal dialogs: consistent inset and a solid border to lift them off the page. */
ParamModal > Vertical, LoginModal > Vertical {
    padding: 1 2;
    border: round $primary;
}
"""
