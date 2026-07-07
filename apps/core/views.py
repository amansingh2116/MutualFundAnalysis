"""apps/core/views.py - Shared views including registration."""
import re
from html import escape
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe


class RegisterView:
    pass


def register_view(request):
    if request.user.is_authenticated:
        return redirect('funds:home')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your account has been created.')
            return redirect('funds:home')
    else:
        form = UserCreationForm()

    # Style the form fields
    for field in form.fields.values():
        field.widget.attrs.setdefault('class', 'form-control')

    return render(request, 'registration/register.html', {'form': form})


PDF_GUIDES_DIR = Path(settings.BASE_DIR) / 'Resources' / 'PDF Guides' / 'pdfs'
BLOGS_DIR = Path(settings.BASE_DIR) / 'Resources' / 'Blogs'
IPO_BLOG_PATH = BLOGS_DIR / 'ipo_analysis.md'
IPO_BLOG_IMAGES_DIR = BLOGS_DIR / 'images' / 'ipo_analysis'

PDF_GUIDE_COPY = {
    'Goals.pdf': {
        'title': 'Goal-Based Investing',
        'description': 'A practical guide to mapping mutual fund choices to time horizons, priorities, and milestones.',
        'accent': 'Goal',
    },
    'MF_Booklet.pdf': {
        'title': 'Mutual Fund Basics',
        'description': 'A concise primer for understanding schemes, NAV, returns, categories, and portfolio fit.',
        'accent': 'MF',
    },
    'MutualFundBook.pdf': {
        'title': 'Mutual Fund Handbook',
        'description': 'A broader reference guide for fund concepts, investor behavior, and long-term decision making.',
        'accent': 'Book',
    },
    'Risks.pdf': {
        'title': 'Risk Awareness Guide',
        'description': 'Learn the risk types behind mutual funds and how to think about volatility, drawdowns, and suitability.',
        'accent': 'Risk',
    },
    'fundamental.pdf': {
        'title': 'Fundamental Analysis and Financial Modelling',
        'description': 'A stock-analysis guide covering business fundamentals, financial information sources, investing styles, and valuation thinking.',
        'accent': 'Fund',
    },
    'technical.pdf': {
        'title': 'Technical Analysis Guide',
        'description': 'A practical guide to reading price, volume, market psychology, trend structure, and the demand-supply forces behind charts.',
        'accent': 'Tech',
    },
    'value.pdf': {
        'title': 'Value Investing and Analysis',
        'description': 'A long-term investing guide focused on saving discipline, compounding, inflation, value investing, and analytical investing habits.',
        'accent': 'Value',
    },
    'ipo_project_report.pdf': {
        'title': 'Indian IPO Research Project Report',
        'description': 'A formal research report testing Indian IPO listing gains, GMP, subscription filters, holding-period returns, and ML screening strategies.',
        'accent': 'IPO',
    },
}

BLOG_IMAGE_PATTERN = re.compile(r'!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)')
INLINE_CODE_PATTERN = re.compile(r'`([^`]+)`')
INLINE_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
INLINE_BOLD_PATTERN = re.compile(r'\*\*([^*]+)\*\*')
INLINE_ITALIC_PATTERN = re.compile(r'(?<!\*)\*([^*\n]+)\*(?!\*)')


def _pdf_guides():
    guides = []
    if not PDF_GUIDES_DIR.exists():
        return guides

    for pdf_path in sorted(PDF_GUIDES_DIR.glob('*.pdf'), key=lambda p: p.stem.lower()):
        meta = PDF_GUIDE_COPY.get(pdf_path.name, {})
        guides.append({
            'filename': pdf_path.name,
            'title': meta.get('title', pdf_path.stem.replace('_', ' ')),
            'description': meta.get('description', 'A mutual fund learning guide from the local PDF library.'),
            'accent': meta.get('accent', pdf_path.stem[:4].upper()),
            'size_kb': max(1, round(pdf_path.stat().st_size / 1024)),
        })
    return guides


def _safe_file_in_dir(base_dir, filename):
    safe_path = (base_dir / Path(filename).name).resolve()
    try:
        safe_path.relative_to(base_dir.resolve())
    except ValueError:
        raise Http404('File not found')
    return safe_path


def _format_inline(text):
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


def _blog_image_url(src):
    normalized = src.strip()
    if normalized.startswith('images/ipo_analysis/'):
        return reverse('core:learn_blog_image', args=[Path(normalized).name])
    return normalized


def _render_markdown_table(lines):
    headers = [cell.strip() for cell in lines[0].strip('|').split('|')]
    body_rows = lines[2:]
    html = ['<div class="article-table-wrap"><table class="article-table"><thead><tr>']
    html.extend(f'<th>{_format_inline(header)}</th>' for header in headers)
    html.append('</tr></thead><tbody>')
    for row in body_rows:
        cells = [cell.strip() for cell in row.strip('|').split('|')]
        html.append('<tr>')
        html.extend(f'<td>{_format_inline(cell)}</td>' for cell in cells)
        html.append('</tr>')
    html.append('</tbody></table></div>')
    return ''.join(html)


def _render_blog_markdown(markdown_text):
    html = []
    paragraph = []
    list_items = []
    lines = markdown_text.splitlines()
    index = 0

    def flush_paragraph():
        if paragraph:
            html.append(f'<p>{" ".join(_format_inline(item) for item in paragraph)}</p>')
            paragraph.clear()

    def flush_list():
        if list_items:
            html.append('<ul>')
            html.extend(f'<li>{_format_inline(item)}</li>' for item in list_items)
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
                html.append(_render_markdown_table(table_lines))
                continue

        image_match = BLOG_IMAGE_PATTERN.fullmatch(line)
        if image_match:
            flush_paragraph()
            flush_list()
            src = _blog_image_url(image_match.group('src'))
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
            html.append(f'<h{level}>{_format_inline(text)}</h{level}>')
            index += 1
            continue

        if line.startswith('>'):
            flush_paragraph()
            flush_list()
            quote = line.lstrip('>').strip()
            html.append(f'<blockquote>{_format_inline(quote)}</blockquote>')
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


def _ipo_blog_summary():
    title = 'Indian IPO Analysis: What the Data Says'
    description = (
        'A beginner-friendly walkthrough of Indian IPO listing gains, GMP, '
        'subscription demand, holding periods, and model-based screening.'
    )

    if IPO_BLOG_PATH.exists():
        for line in IPO_BLOG_PATH.read_text(encoding='utf-8').splitlines():
            if line.startswith('# '):
                title = line[2:].strip()
                break

    return {
        'title': title,
        'description': description,
        'tag': 'Project blog',
        'read_time': '12 min read',
    }


def learn_resources_view(request):
    return render(request, 'learn/resources.html', {
        'pdf_guides': _pdf_guides(),
        'featured_blog': _ipo_blog_summary(),
    })


def learn_pdf_view(request, filename):
    pdf_path = _safe_file_in_dir(PDF_GUIDES_DIR, filename)

    if not pdf_path.exists() or pdf_path.suffix.lower() != '.pdf':
        raise Http404('Guide not found')

    return FileResponse(pdf_path.open('rb'), content_type='application/pdf', filename=pdf_path.name)


def learn_blog_detail_view(request):
    if not IPO_BLOG_PATH.exists():
        raise Http404('Blog not found')

    markdown_text = IPO_BLOG_PATH.read_text(encoding='utf-8')
    blog = _ipo_blog_summary()
    blog['html'] = _render_blog_markdown(markdown_text)
    blog['report_filename'] = 'ipo_project_report.pdf'
    return render(request, 'learn/blog_detail.html', {'blog': blog})


def learn_blog_image_view(request, filename):
    image_path = _safe_file_in_dir(IPO_BLOG_IMAGES_DIR, filename)
    content_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp',
    }

    content_type = content_types.get(image_path.suffix.lower())
    if not image_path.exists() or not content_type:
        raise Http404('Image not found')

    return FileResponse(image_path.open('rb'), content_type=content_type)


def learn_community_view(request):
    posts = [
        {
            'author': 'Aman',
            'title': 'How do you decide between index and active funds?',
            'body': 'I am comparing cost, consistency, and downside behavior. Would love to collect simple frameworks from other investors.',
            'meta': 'Discussion starter',
            'replies': [
                'Look at rolling returns and category rank persistence, not just one-year performance.',
                'For core allocation, I prefer simple funds. For satellite allocation, I compare fund manager style.',
            ],
        },
        {
            'author': 'Community',
            'title': 'Share your rebalancing rules',
            'body': 'A placeholder thread for portfolio rebalancing ideas, mistakes, and practical rules of thumb.',
            'meta': 'Pinned prompt',
            'replies': ['Add your first real community replies here when the feature is connected.'],
        },
    ]
    return render(request, 'learn/community.html', {'posts': posts})
