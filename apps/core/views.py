"""apps/core/views.py - Shared views including registration."""
import json
import mimetypes
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db import DatabaseError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.text import slugify

from .content import (
    BLOGS_DIR,
    IMAGE_SUFFIXES,
    PDF_CATEGORY_CHAPTERS,
    PDF_CATEGORY_HANDBOOK,
    PDF_CATEGORY_OTHER,
    PDF_GUIDE_PDFS_DIR,
    PDF_GUIDES_DIR,
    PDF_SUFFIXES,
    _parse_tags,
    first_markdown_heading,
    first_markdown_paragraph,
    metadata_slug,
    parse_front_matter,
    path_to_base_relative,
    read_pdf_manifest,
    render_blog_markdown,
    resolve_resource_relative,
)
from .models import LearnBlogPost, LearnPDFGuide


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


def _asset_url(relative_path):
    if not relative_path:
        return ''
    return reverse('core:learn_resource_asset', args=[relative_path])


def _guide_card_from_model(guide):
    return {
        'title': guide.title,
        'description': guide.description,
        'accent': guide.accent or guide.title[:5],
        'size_kb': guide.size_kb,
        'cover_url': _asset_url(guide.cover_image_path),
        'pdf_url': reverse('core:learn_pdf_viewer', args=[guide.slug]),
        'source_key': guide.pdf_path,
        'category': guide.category,
        'tags': guide.tag_list(),
        'downloadable': guide.downloadable,
    }


def _blog_card_from_model(post):
    return {
        'title': post.title,
        'description': post.description,
        'tag': 'Blog',
        'read_time': post.read_time,
        'thumbnail_url': _asset_url(post.thumbnail_path),
        'url': reverse('core:learn_blog_detail', args=[post.slug]),
        'source_key': post.markdown_path,
        'tags': post.tag_list(),
        'sort_order': post.sort_order,
        'featured': post.is_featured,
    }


def _guide_card_from_file(pdf_path, meta, index):
    title = meta.get('title') or pdf_path.stem.replace('_', ' ').replace('-', ' ').title()
    cover = meta.get('cover') or meta.get('cover_image') or ''
    cover_path = path_to_base_relative((PDF_GUIDES_DIR / cover).resolve()) if cover else ''
    raw_tags = meta.get('tags', [])
    viewer_slug = slugify(meta.get('slug') or pdf_path.stem)[:140]
    return {
        'title': title,
        'description': meta.get('description') or 'A learning guide from the local PDF library.',
        'accent': meta.get('accent') or title[:5],
        'size_kb': max(1, round(pdf_path.stat().st_size / 1024)),
        'cover_url': _asset_url(cover_path),
        'pdf_url': reverse('core:learn_pdf_viewer', args=[viewer_slug]),
        'sort_order': int(meta.get('order') or meta.get('sort_order') or index * 10),
        'source_key': path_to_base_relative(pdf_path),
        'category': meta.get('category') or PDF_CATEGORY_OTHER,
        'tags': _parse_tags(raw_tags if isinstance(raw_tags, str) else json.dumps(raw_tags)),
        'downloadable': bool(meta.get('downloadable', False)),
    }


def _blog_from_file(markdown_path, index=1):
    markdown_text = markdown_path.read_text(encoding='utf-8')
    meta, body = parse_front_matter(markdown_text)
    title = meta.get('title') or first_markdown_heading(body, markdown_path.stem.replace('_', ' ').title())
    thumbnail = meta.get('thumbnail') or meta.get('cover') or meta.get('cover_image') or ''
    thumbnail_path = path_to_base_relative((markdown_path.parent / thumbnail).resolve()) if thumbnail else ''
    raw_tags = meta.get('tags', [])
    return {
        'slug': metadata_slug(meta, markdown_path),
        'title': title,
        'description': meta.get('description') or first_markdown_paragraph(body, 'A learning article from the local blog library.'),
        'tag': 'Blog',
        'read_time': meta.get('read_time') or '5 min read',
        'thumbnail_url': _asset_url(thumbnail_path),
        'url': reverse('core:learn_blog_detail', args=[metadata_slug(meta, markdown_path)]),
        'sort_order': int(meta.get('order') or meta.get('sort_order') or index * 10),
        'markdown_path': markdown_path,
        'markdown_text': markdown_text,
        'source_key': path_to_base_relative(markdown_path),
        'tags': _parse_tags(raw_tags if isinstance(raw_tags, list) else json.dumps(raw_tags)),
        'featured': bool(meta.get('featured', False)),
    }


def _file_pdf_guides():
    manifest = read_pdf_manifest()
    guides = []
    if not PDF_GUIDE_PDFS_DIR.exists():
        return guides

    pdf_paths = sorted(PDF_GUIDE_PDFS_DIR.glob('*.pdf'), key=lambda item: item.name.lower())
    for index, pdf_path in enumerate(pdf_paths, start=1):
        key = pdf_path.relative_to(PDF_GUIDES_DIR).as_posix()
        meta = manifest.get(key, {})
        if not bool(meta.get('published', meta.get('is_published', True))):
            continue
        guides.append(_guide_card_from_file(pdf_path, meta, index))
    return sorted(guides, key=lambda item: (item['sort_order'], item['title']))


def _file_blog_posts():
    blogs = []
    if not BLOGS_DIR.exists():
        return blogs

    markdown_paths = sorted(BLOGS_DIR.glob('*.md'), key=lambda item: item.name.lower())
    for index, markdown_path in enumerate(markdown_paths, start=1):
        blog = _blog_from_file(markdown_path, index)
        _meta, _body = parse_front_matter(blog['markdown_text'])
        if not bool(_meta.get('published', _meta.get('is_published', True))):
            continue
        blogs.append(blog)
    return sorted(blogs, key=lambda item: (item['sort_order'], item['title']))


def _collect_all_guides_and_blogs():
    """Return (all_pdf_guides, all_blog_posts) merged from DB + files."""
    try:
        all_pdf_keys = set(LearnPDFGuide.objects.values_list('pdf_path', flat=True))
        all_blog_keys = set(LearnBlogPost.objects.values_list('markdown_path', flat=True))
        pdf_guides = [
            _guide_card_from_model(guide)
            for guide in LearnPDFGuide.objects.filter(is_published=True).order_by('sort_order', 'title')
        ]
        blog_posts = [
            _blog_card_from_model(post)
            for post in LearnBlogPost.objects.filter(is_published=True).order_by('sort_order', 'title')
        ]
        pdf_guides.extend(guide for guide in _file_pdf_guides() if guide['source_key'] not in all_pdf_keys)
        blog_posts.extend(blog for blog in _file_blog_posts() if blog['source_key'] not in all_blog_keys)
    except DatabaseError:
        pdf_guides = _file_pdf_guides()
        blog_posts = _file_blog_posts()

    pdf_guides = sorted(pdf_guides, key=lambda item: (item.get('sort_order', 100), item['title']))
    blog_posts = sorted(blog_posts, key=lambda item: (item.get('sort_order', 100), item['title']))
    return pdf_guides, blog_posts


def _collect_all_tags(pdf_guides, blog_posts):
    """Return sorted unique tag lists for PDFs and blogs."""
    pdf_tags = sorted({tag for guide in pdf_guides for tag in guide.get('tags', [])})
    blog_tags = sorted({tag for blog in blog_posts for tag in blog.get('tags', [])})
    return pdf_tags, blog_tags


def learn_resources_view(request):
    """Redirect old resources overview to the dedicated PDF guides page."""
    return redirect('core:learn_pdf_guides')


def learn_pdf_guides_view(request):
    """Dedicated full-page view for PDF Guides."""
    pdf_guides, _blog_posts = _collect_all_guides_and_blogs()
    pdf_tags, _ = _collect_all_tags(pdf_guides, [])

    chapter_guides = [g for g in pdf_guides if g.get('category') == PDF_CATEGORY_CHAPTERS]
    handbook_guides = [g for g in pdf_guides if g.get('category') == PDF_CATEGORY_HANDBOOK]
    other_guides = [g for g in pdf_guides if g.get('category') == PDF_CATEGORY_OTHER]

    active_tag = request.GET.get('tag', '').strip()

    return render(request, 'learn/pdf_guides.html', {
        'pdf_guides': pdf_guides,
        'chapter_guides': chapter_guides,
        'handbook_guides': handbook_guides,
        'other_guides': other_guides,
        'pdf_tags': pdf_tags,
        'active_tag': active_tag,
    })


def learn_blogs_view(request):
    """Dedicated full-page view for Blogs."""
    _pdf_guides, blog_posts = _collect_all_guides_and_blogs()
    _, blog_tags = _collect_all_tags([], blog_posts)

    active_tag = request.GET.get('tag', '').strip()

    return render(request, 'learn/blogs.html', {
        'blog_posts': blog_posts,
        'blog_tags': blog_tags,
        'active_tag': active_tag,
    })


def _serve_pdf_response(pdf_path, as_attachment=False):
    """Serve raw PDF bytes with security headers that discourage saving."""
    if not pdf_path.exists() or pdf_path.suffix.lower() not in PDF_SUFFIXES:
        raise Http404('Guide not found')
    response = FileResponse(
        pdf_path.open('rb'),
        content_type='application/pdf',
        as_attachment=as_attachment,
        filename=pdf_path.name if as_attachment else None,
    )
    # Prevent search engine indexing of raw PDF bytes endpoint
    response['X-Robots-Tag'] = 'noindex, nofollow'
    # Instruct browser to display inline — not trigger Save As
    if not as_attachment:
        response['Content-Disposition'] = f'inline; filename="{pdf_path.name}"'
    # Prevent caching so the URL cannot be easily harvested and replayed
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    return response


def _find_pdf_path_by_slug(slug):
    manifest = read_pdf_manifest()
    if not PDF_GUIDE_PDFS_DIR.exists():
        return None

    for pdf_path in PDF_GUIDE_PDFS_DIR.glob('*.pdf'):
        key = pdf_path.relative_to(PDF_GUIDES_DIR).as_posix()
        meta = manifest.get(key, {})
        candidate = slugify(meta.get('slug') or pdf_path.stem)[:140]
        if candidate == slug:
            return pdf_path, meta
    return None, {}


def _guide_meta_by_slug(slug):
    """Return (pdf_path, title, downloadable) for a given slug from DB or manifest.

    The manifest's 'downloadable' field is always preferred over the DB value so
    that editing guides.json takes effect immediately without running sync_content.
    """
    manifest_path, manifest_meta = _find_pdf_path_by_slug(slug)
    # Manifest is the live source of truth for downloadable
    manifest_downloadable = bool(manifest_meta.get('downloadable', False)) if manifest_meta else False

    try:
        guide = LearnPDFGuide.objects.filter(slug=slug).first()
        if guide and not guide.is_published:
            return None, None, False
        if guide:
            # Use manifest value for downloadable (live control); DB for everything else
            downloadable = manifest_downloadable if manifest_meta else guide.downloadable
            return resolve_resource_relative(guide.pdf_path), guide.title, downloadable
    except DatabaseError:
        pass

    if not manifest_path:
        return None, None, False
    title = manifest_meta.get('title') or manifest_path.stem.replace('_', ' ').replace('-', ' ').title()
    return manifest_path, title, manifest_downloadable


def learn_pdf_viewer_view(request, slug):
    """Render the in-app PDF viewer page — does NOT expose the raw PDF URL in HTML."""
    pdf_path, title, downloadable = _guide_meta_by_slug(slug)
    if not pdf_path:
        raise Http404('Guide not found')
    serve_url = reverse('core:learn_pdf_serve', args=[slug])
    return render(request, 'learn/pdf_viewer.html', {
        'title': title,
        'serve_url': serve_url,
        'downloadable': downloadable,
        'slug': slug,
    })


def learn_pdf_serve_view(request, slug):
    """Serve the raw PDF bytes — only intended to be fetched by PDF.js inside the viewer."""
    pdf_path, _title, downloadable = _guide_meta_by_slug(slug)
    if not pdf_path:
        raise Http404('Guide not found')
    # If ?download=1 is requested AND the guide is downloadable, serve as attachment
    wants_download = request.GET.get('download') == '1'
    as_attachment = wants_download and downloadable
    return _serve_pdf_response(pdf_path, as_attachment=as_attachment)


def learn_pdf_detail_view(request, slug):
    """Legacy — redirect to in-app viewer."""
    return redirect(reverse('core:learn_pdf_viewer', args=[slug]))


def learn_pdf_view(request, filename):
    """Legacy filename-based route — resolve slug and redirect to viewer."""
    safe_name = Path(filename).name
    try:
        guide = LearnPDFGuide.objects.filter(pdf_path__iendswith=f'/{safe_name}', is_published=True).first()
        if guide:
            return redirect(reverse('core:learn_pdf_viewer', args=[guide.slug]))
    except DatabaseError:
        pass
    # Fall back: find by filename in manifest
    manifest = read_pdf_manifest()
    if PDF_GUIDE_PDFS_DIR.exists():
        for pdf_path in PDF_GUIDE_PDFS_DIR.glob('*.pdf'):
            if pdf_path.name == safe_name:
                key = pdf_path.relative_to(PDF_GUIDES_DIR).as_posix()
                meta = manifest.get(key, {})
                candidate_slug = slugify(meta.get('slug') or pdf_path.stem)[:140]
                return redirect(reverse('core:learn_pdf_viewer', args=[candidate_slug]))
    raise Http404('Guide not found')


def _find_blog_file_by_slug(slug):
    for blog in _file_blog_posts():
        if blog['slug'] == slug:
            return blog
    return None


def _report_url():
    try:
        report = LearnPDFGuide.objects.filter(slug='ipo-project-report', is_published=True).first()
        if report:
            return reverse('core:learn_pdf_detail', args=[report.slug])
    except DatabaseError:
        pass

    report_path = PDF_GUIDE_PDFS_DIR / 'ipo_project_report.pdf'
    if report_path.exists():
        return reverse('core:learn_pdf', args=[report_path.name])
    return ''


def learn_blog_detail_view(request, slug):
    blog = None
    markdown_path = None
    markdown_text = None
    try:
        post = LearnBlogPost.objects.filter(slug=slug).first()
        if post and not post.is_published:
            raise Http404('Blog not found')
        if post:
            markdown_path = resolve_resource_relative(post.markdown_path)
            if not markdown_path.exists() or markdown_path.suffix.lower() != '.md':
                raise Http404('Blog not found')
            markdown_text = markdown_path.read_text(encoding='utf-8')
            blog = _blog_card_from_model(post)
    except DatabaseError:
        pass

    if not blog:
        blog = _find_blog_file_by_slug(slug)
        if not blog:
            raise Http404('Blog not found')
        markdown_path = blog['markdown_path']
        markdown_text = blog['markdown_text']

    blog['html'] = render_blog_markdown(markdown_text, markdown_path)
    blog['report_url'] = _report_url()
    return render(request, 'learn/blog_detail.html', {'blog': blog})


def learn_resource_asset_view(request, resource_path):
    try:
        asset_path = resolve_resource_relative(resource_path)
    except ValueError:
        raise Http404('Asset not found')

    if not asset_path.exists() or asset_path.suffix.lower() not in IMAGE_SUFFIXES:
        raise Http404('Asset not found')

    content_type = mimetypes.guess_type(asset_path.name)[0] or 'application/octet-stream'
    return FileResponse(asset_path.open('rb'), content_type=content_type)


def learn_blog_image_view(request, filename):
    legacy_path = BLOGS_DIR / 'images' / 'ipo_analysis' / Path(filename).name
    return learn_resource_asset_view(request, path_to_base_relative(legacy_path))


@login_required(login_url='/accounts/login/')
def learn_community_view(request):
    return render(request, 'learn/community.html', {})


# ── Legal / Info pages ────────────────────────────────────────────────────────

def about_view(request):
    """About page — mission, philosophy, what we cover."""
    return render(request, 'legal/about.html', {})


def terms_view(request):
    """Terms of Service."""
    return render(request, 'legal/terms.html', {})


def privacy_view(request):
    """Privacy Policy."""
    return render(request, 'legal/privacy.html', {})


def contact_view(request):
    """Contact page with a simple message form."""
    submitted = False
    if request.method == 'POST':
        # No external mail service required — just show success message.
        submitted = True
        messages.success(request, "Thanks for reaching out! We'll get back to you shortly.")
    return render(request, 'legal/contact.html', {'submitted': submitted})

