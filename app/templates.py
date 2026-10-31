import html
import re
from typing import List, Optional
from app.db import LessonExerciseRow


def markdown_to_clean_html(md_text: str) -> str:
    """Converts clean markdown lesson text into dark-theme email-safe HTML."""
    if not md_text:
        return ""

    escaped = html.escape(md_text.strip())

    # Format Markdown Headers (###, ##, #)
    escaped = re.sub(
        r"^###\s+(.+)$",
        r'<h3 style="color: #58A6FF; font-size: 16px; margin: 22px 0 8px 0; font-weight: 700;">\1</h3>',
        escaped,
        flags=re.MULTILINE,
    )
    escaped = re.sub(
        r"^##\s+(.+)$",
        r'<h2 style="color: #FFFFFF; font-size: 18px; margin: 26px 0 10px 0; font-weight: 700;">\1</h2>',
        escaped,
        flags=re.MULTILINE,
    )
    escaped = re.sub(
        r"^#\s+(.+)$",
        r'<h1 style="color: #FFFFFF; font-size: 22px; margin: 28px 0 12px 0; font-weight: 800;">\1</h1>',
        escaped,
        flags=re.MULTILINE,
    )

    # Format bold (**text**)
    escaped = re.sub(r"\*\*(.+?)\*\*", r'<strong style="color: #FFFFFF;">\1</strong>', escaped)
    # Format italic (*text*)
    escaped = re.sub(r"\*(.+?)\*", r'<em style="color: #D2A8FF;">\1</em>', escaped)

    # Format Pro-Tips (💡 Pro-Tip: ...)
    escaped = re.sub(
        r"(💡\s*(?:Pro-Tip|Tip):?[^\n]+)",
        r'<div style="background-color: #1C2128; border-left: 3px solid #D29922; padding: 12px 14px; margin: 16px 0; border-radius: 4px; color: #E6EDF3; font-size: 13.5px; line-height: 1.5;">\1</div>',
        escaped,
    )

    # Format phonetic brackets (e.g. [tsvy], [nool])
    escaped = re.sub(
        r"(\[[a-zA-Z0-9\s/_\-ÄÖÜäöüß]+\])",
        r'<span style="color: #7EE787; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 13px;">\1</span>',
        escaped,
    )

    # Convert linebreaks and paragraph spacing
    paragraphs = escaped.split("\n\n")
    formatted_paras = []
    for p in paragraphs:
        p_clean = p.strip()
        if not p_clean:
            continue
        if p_clean.startswith("<h") or p_clean.startswith("<div"):
            formatted_paras.append(p_clean.replace("\n", "<br>"))
        else:
            p_with_breaks = p_clean.replace("\n", "<br>")
            formatted_paras.append(
                f'<p style="margin: 0 0 14px 0; color: #C9D1D9; font-size: 14.5px; line-height: 1.65;">{p_with_breaks}</p>'
            )

    return "\n".join(formatted_paras)


def render_plain_text_email(
    student_name: str,
    course_name: str,
    lesson_id: int,
    theory_summary: Optional[str],
    exercises: List[LessonExerciseRow],
    magic_link_url: str,
) -> str:
    """Renders clean markdown plain text lesson email without exercises list."""
    lines = []
    if theory_summary:
        lines.append(theory_summary.strip())
    else:
        lines.append(f"🇩🇪 German Micro-Lesson #{lesson_id:03d}: {course_name}")

    lines.extend([
        "",
        "---",
        "🎯 START INTERACTIVE EXERCISES ONLINE:",
        magic_link_url,
        "",
        "(5 interactive exercises • Valid for 7 days • Zero password/login required)",
    ])

    return "\n".join(lines)


def render_html_email(
    student_name: str,
    course_name: str,
    lesson_id: int,
    theory_summary: Optional[str],
    exercises: List[LessonExerciseRow],
    magic_link_url: str,
) -> str:
    """Renders simple, elegant markdown-styled dark HTML email without exercise questions."""
    safe_course = html.escape(course_name)
    safe_url = html.escape(magic_link_url)

    content_html = markdown_to_clean_html(theory_summary) if theory_summary else f"<p>Lektion #{lesson_id:03d} vorbereitet.</p>"

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_course} — Lektion #{lesson_id:03d}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0A0A0A; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #C9D1D9; -webkit-font-smoothing: antialiased;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #0A0A0A; padding: 24px 12px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" style="max-width: 620px; background-color: #121212; border: 1px solid #262626; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6);" cellspacing="0" cellpadding="0" border="0">
                    
                    <!-- Top Category Bar -->
                    <tr>
                        <td style="padding: 20px 24px 16px 24px; border-bottom: 1px solid #1F1F1F;">
                            <div style="display: inline-block; font-size: 11px; font-weight: 700; color: #00E5FF; text-transform: uppercase; letter-spacing: 1px;">
                                🇩🇪 {safe_course} • Lektion #{lesson_id:03d}
                            </div>
                        </td>
                    </tr>

                    <!-- Markdown Content Body -->
                    <tr>
                        <td style="padding: 24px; font-size: 14.5px; line-height: 1.65; color: #C9D1D9;">
                            {content_html}

                            <!-- Interactive Magic Link Call-to-Action (Exercises Online) -->
                            <div style="margin-top: 32px; padding: 20px; background-color: #181818; border: 1px solid #00E5FF; border-radius: 8px; text-align: center; box-shadow: 0 4px 14px rgba(0, 229, 255, 0.12);">
                                <p style="margin: 0 0 14px 0; color: #FFFFFF; font-size: 14px; font-weight: 600;">
                                    🎯 Start your 5 interactive exercises online (Zero login required):
                                </p>
                                
                                <div style="margin-bottom: 12px;">
                                    <a href="{safe_url}" target="_blank" style="display: inline-block; padding: 12px 28px; background-color: #00E5FF; color: #0A0A0A; text-decoration: none; font-size: 14px; font-weight: 800; border-radius: 6px; letter-spacing: 0.5px;">
                                        Start Exercises Online →
                                    </a>
                                </div>

                                <div style="font-size: 11.5px; color: #888888; word-break: break-all;">
                                    Direct Link: <a href="{safe_url}" style="color: #00E5FF; text-decoration: underline;">{safe_url}</a>
                                </div>
                            </div>
                        </td>
                    </tr>

                    <!-- Simple Footer -->
                    <tr>
                        <td style="padding: 16px 24px; background-color: #0D0D0D; border-top: 1px solid #1F1F1F; text-align: center;">
                            <p style="margin: 0; font-size: 11.5px; color: #666666;">
                                Deutsch Daily • Micro-Learning Service • Ephemeral Link valid for 7 days
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
