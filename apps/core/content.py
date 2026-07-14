"""Helpers for Learn content stored under the local Resources folder."""
import json
import re
from html import escape
from pathlib import Path

from django.conf import settings
from django.urls import reverse
from django.utils.text import slugify
from django.utils.safestring import mark_safe

RESOURCES_DIR = Path(settings.BASE_DIR) / 'Resources'
BLOGS_DIR = RESOURCES_DIR / 'Blogs'
PDF_GUIDES_DIR = RESOURCES_DIR / 'PDF Guides'
PDF_GUIDE_PDFS_DIR = PDF_GUIDES_DIR / 'pdfs'
PDF_GUIDE_MANIFEST = PDF_GUIDES_DIR / 'guides.json'

PDF_CATEGORY_CHAPTERS = 'chapters'
PDF_CATEGORY_HANDBOOK = 'handbook'
PDF_CATEGORY_OTHER = 'other'

IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
PDF_SUFFIXES = {'.pdf'}

BLOG_IMAGE_PATTERN = re.compile(r'!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)')
INLINE_CODE_PATTERN = re.compile(r'`([^`]+)`')
INLINE_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
INLINE_BOLD_PATTERN = re.compile(r'\*\*([^*]+)\*\*')
INLINE_ITALIC_PATTERN = re.compile(r'(?<!\*)\*([^*\n]+)\*(?!\*)')


def path_to_base_relative(path):
    resolved = Path(path).resolve()
    return resolved.relative_to(Path(settings.BASE_DIR).resolve()).as_posix()


def resolve_base_relative(relative_path):
    resolved = (Path(settings.BASE_DIR) / relative_path).resolve()
    resolved.relative_to(Path(settings.BASE_DIR).resolve())
    return resolved


def resolve_resource_relative(relative_path):
    resolved = resolve_base_relative(relative_path)
    resolved.relative_to(RESOURCES_DIR.resolve())
    return resolved


def parse_front_matter(markdown_text):
    lines = markdown_text.splitlines()
    if not lines or lines[0].strip() != '---':
        return {}, markdown_text

    for index in range(1, len(lines)):
        if lines[index].strip() == '---':
            metadata = _parse_metadata_lines(lines[1:index])
            body = '\n'.join(lines[index + 1:]).lstrip('\n')
            return metadata, body

    return {}, markdown_text


def _parse_metadata_lines(lines):
    metadata = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith('#') or ':' not in line:
            continue
        key, value = line.split(':', 1)
        metadata[key.strip().lower().replace('-', '_')] = _parse_metadata_value(value.strip())
    return metadata


def _parse_metadata_value(value):
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lower = value.lower()
    if lower in {'true', 'yes'}:
        return True
    if lower in {'false', 'no'}:
        return False
    if lower in {'null', 'none'}:
        return ''
    try:
        return int(value)
    except ValueError:
        return value


def _parse_tags(raw):
    """Parse tags from a JSON array or comma-separated string into a sorted list."""
    import json as _json
    if not raw:
        return []
    raw = str(raw).strip()
    if raw.startswith('['):
        try:
            return sorted({str(t).strip() for t in _json.loads(raw) if str(t).strip()})
        except (ValueError, TypeError):
            pass
    return sorted({t.strip() for t in raw.split(',') if t.strip()})


def first_markdown_heading(markdown_text, fallback):
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('# '):
            return stripped[2:].strip()
    return fallback


def first_markdown_paragraph(markdown_text, fallback=''):
    skip_prefixes = ('#', '!', '|', '---', '>', '-')
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(skip_prefixes):
            return stripped.strip('*')
    return fallback


def metadata_slug(meta, path):
    return slugify(meta.get('slug') or Path(path).stem)[:140]




def read_pdf_manifest():
    if not PDF_GUIDE_MANIFEST.exists():
        return {}

    with PDF_GUIDE_MANIFEST.open('r', encoding='utf-8') as manifest_file:
        data = json.load(manifest_file)

    if isinstance(data, dict) and 'guides' in data:
        rows = data['guides']
    elif isinstance(data, dict):
        rows = []
        for file_path, metadata in data.items():
            item = {'file': file_path}
            if isinstance(metadata, dict):
                item.update(metadata)
            rows.append(item)
    elif isinstance(data, list):
        rows = data
    else:
        return {}

    manifest = {}
    for item in rows:
        if not isinstance(item, dict) or not item.get('file'):
            continue
        manifest[Path(item['file']).as_posix()] = item
    return manifest


def format_inline(text):
    formatted = escape(text)
    formatted = INLINE_CODE_PATTERN.sub(r'<code>\1</code>', formatted)
    formatted = INLINE_LINK_PATTERN.sub(
        lambda match: (
            f'<a href="{escape(match.group(2), quote=True)}" target="_blank" '
            f'rel="noopener">{match.group(1)}</a>'
        ),
        formatted,
    )
    formatted = INLINE_BOLD_PATTERN.sub(r'<strong>\1</strong>', formatted)
    formatted = INLINE_ITALIC_PATTERN.sub(r'<em>\1</em>', formatted)
    return formatted


def render_markdown_table(lines):
    headers = [cell.strip() for cell in lines[0].strip('|').split('|')]
    body_rows = lines[2:]
    html = ['<div class="article-table-wrap"><table class="article-table"><thead><tr>']
    html.extend(f'<th>{format_inline(header)}</th>' for header in headers)
    html.append('</tr></thead><tbody>')
    for row in body_rows:
        cells = [cell.strip() for cell in row.strip('|').split('|')]
        html.append('<tr>')
        html.extend(f'<td>{format_inline(cell)}</td>' for cell in cells)
        html.append('</tr>')
    html.append('</tbody></table></div>')
    return ''.join(html)


def default_asset_url(markdown_path, src):
    src = src.strip()
    if src.startswith(('http://', 'https://', '/', 'data:')):
        return src

    asset_path = (Path(markdown_path).parent / src).resolve()
    try:
        asset_path.relative_to(RESOURCES_DIR.resolve())
    except ValueError:
        return src

    relative_path = path_to_base_relative(asset_path)
    return reverse('core:learn_resource_asset', args=[relative_path])


def render_blog_markdown(markdown_text, markdown_path):
    _metadata, body = parse_front_matter(markdown_text)
    html = []
    paragraph = []
    list_items = []
    lines = body.splitlines()
    index = 0

    def flush_paragraph():
        if paragraph:
            html.append(f'<p>{" ".join(format_inline(item) for item in paragraph)}</p>')
            paragraph.clear()

    def flush_list():
        if list_items:
            html.append('<ul>')
            html.extend(f'<li>{format_inline(item)}</li>' for item in list_items)
            html.append('</ul>')
            list_items.clear()

    while index < len(lines):
        line = lines[index].strip()

        if not line:
            flush_paragraph()
            flush_list()
            index += 1
            continue

        if line.startswith('|') and index + 1 < len(lines):
            separator = lines[index + 1].strip().replace('|', '').replace(' ', '')
            if separator and set(separator) <= {'-', ':'}:
                flush_paragraph()
                flush_list()
                table_lines = [line, lines[index + 1].strip()]
                index += 2
                while index < len(lines) and lines[index].strip().startswith('|'):
                    table_lines.append(lines[index].strip())
                    index += 1
                html.append(render_markdown_table(table_lines))
                continue

        image_match = BLOG_IMAGE_PATTERN.fullmatch(line)
        if image_match:
            flush_paragraph()
            flush_list()
            src = default_asset_url(markdown_path, image_match.group('src'))
            alt = escape(image_match.group('alt'), quote=True)
            html.append(f'<figure class="article-figure"><img src="{src}" alt="{alt}"></figure>')
            index += 1
            continue

        if line.startswith('---'):
            flush_paragraph()
            flush_list()
            html.append('<hr>')
            index += 1
            continue

        if line.startswith('#'):
            flush_paragraph()
            flush_list()
            level = min(len(line) - len(line.lstrip('#')), 4)
            text = line[level:].strip()
            html.append(f'<h{level}>{format_inline(text)}</h{level}>')
            index += 1
            continue

        if line.startswith('>'):
            flush_paragraph()
            flush_list()
            quote = line.lstrip('>').strip()
            html.append(f'<blockquote>{format_inline(quote)}</blockquote>')
            index += 1
            continue

        if line.startswith('- '):
            flush_paragraph()
            list_items.append(line[2:].strip())
            index += 1
            continue

        paragraph.append(line)
        index += 1

    flush_paragraph()
    flush_list()
    return mark_safe('\n'.join(html))
