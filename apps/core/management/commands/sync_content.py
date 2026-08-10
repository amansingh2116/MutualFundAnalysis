"""Sync Learn resources from files under the Resources folder."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from apps.core.content import (
    BLOGS_DIR,
    PDF_GUIDE_PDFS_DIR,
    PDF_GUIDES_DIR,
    first_markdown_heading,
    first_markdown_paragraph,
    metadata_slug,
    parse_front_matter,
    path_to_base_relative,
    read_pdf_manifest,
    _parse_tags,
)
from apps.core.models import LearnBlogPost, LearnPDFGuide


class Command(BaseCommand):
    help = 'Sync Learn PDF guides and markdown blogs from the Resources folder.'

    def handle(self, *args, **options):
        synced_pdfs = self.sync_pdf_guides()
        synced_blogs = self.sync_blog_posts()
        self.stdout.write(self.style.SUCCESS(f'Synced {synced_pdfs} PDF guides and {synced_blogs} blog posts.'))

    def sync_pdf_guides(self):
        manifest = read_pdf_manifest()
        seen_paths = []
        count = 0

        if not PDF_GUIDE_PDFS_DIR.exists():
            self.stdout.write(self.style.WARNING(f'PDF folder not found: {PDF_GUIDE_PDFS_DIR}'))
            return 0

        for index, pdf_path in enumerate(sorted(PDF_GUIDE_PDFS_DIR.glob('*.pdf'), key=lambda item: item.name.lower()), start=1):
            manifest_key = pdf_path.relative_to(PDF_GUIDES_DIR).as_posix()
            meta = manifest.get(manifest_key, {})
            title = meta.get('title') or pdf_path.stem.replace('_', ' ').replace('-', ' ').title()
            description = meta.get('description') or 'A learning guide from the local PDF library.'
            slug = slugify(meta.get('slug') or pdf_path.stem)[:140]
            cover = meta.get('cover') or meta.get('cover_image') or ''
            cover_path = ''
            if cover:
                cover_path = path_to_base_relative((PDF_GUIDES_DIR / cover).resolve())

            relative_pdf_path = path_to_base_relative(pdf_path)
            seen_paths.append(relative_pdf_path)
            LearnPDFGuide.objects.update_or_create(
                pdf_path=relative_pdf_path,
                defaults={
                    'slug': slug,
                    'title': title,
                    'description': description,
                    'cover_image_path': cover_path,
                    'accent': (meta.get('accent') or title[:5])[:90],
                    'size_kb': max(1, round(pdf_path.stat().st_size / 1024)),
                    'sort_order': int(meta.get('order') or meta.get('sort_order') or index * 10),
                    'is_published': bool(meta.get('published', meta.get('is_published', True))),
                    'downloadable': bool(meta.get('downloadable', False)),
                    'category': (meta.get('category') or 'other')[:45],
                    'tags': _tags_to_json(meta.get('tags', [])),
                    'synced_at': timezone.now(),
                },
            )
            count += 1

        LearnPDFGuide.objects.exclude(pdf_path__in=seen_paths).update(is_published=False, synced_at=timezone.now())
        return count

    def sync_blog_posts(self):
        seen_paths = []
        count = 0

        if not BLOGS_DIR.exists():
            self.stdout.write(self.style.WARNING(f'Blogs folder not found: {BLOGS_DIR}'))
            return 0

        markdown_files = sorted(BLOGS_DIR.glob('*.md'), key=lambda item: item.name.lower())
        for index, markdown_path in enumerate(markdown_files, start=1):
            markdown_text = markdown_path.read_text(encoding='utf-8')
            meta, body = parse_front_matter(markdown_text)
            title = meta.get('title') or first_markdown_heading(body, markdown_path.stem.replace('_', ' ').title())
            description = meta.get('description') or first_markdown_paragraph(body, 'A learning article from the local blog library.')
            thumbnail = meta.get('thumbnail') or meta.get('cover') or meta.get('cover_image') or ''
            thumbnail_path = ''
            if thumbnail:
                thumbnail_path = path_to_base_relative((markdown_path.parent / thumbnail).resolve())

            relative_markdown_path = path_to_base_relative(markdown_path)
            seen_paths.append(relative_markdown_path)
            LearnBlogPost.objects.update_or_create(
                markdown_path=relative_markdown_path,
                defaults={
                    'slug': metadata_slug(meta, markdown_path),
                    'title': title,
                    'description': description,
                    'thumbnail_path': thumbnail_path,
                    'read_time': meta.get('read_time') or estimate_read_time(body),
                    'sort_order': int(meta.get('order') or meta.get('sort_order') or index * 10),
                    'is_published': bool(meta.get('published', meta.get('is_published', True))),
                    'is_featured': bool(meta.get('featured', False)),
                    'tags': _tags_to_json(meta.get('tags', [])),
                    'synced_at': timezone.now(),
                },
            )
            count += 1

        LearnBlogPost.objects.exclude(markdown_path__in=seen_paths).update(is_published=False, synced_at=timezone.now())
        return count


def estimate_read_time(markdown_text):
    words = [word for word in markdown_text.replace('|', ' ').split() if word.strip()]
    minutes = max(1, round(len(words) / 220))
    return f'{minutes} min read'


def _tags_to_json(raw):
    """Safely convert a tag value (list or string) to a JSON array string."""
    if isinstance(raw, list):
        return json.dumps([str(t).strip() for t in raw if str(t).strip()])
    if isinstance(raw, str) and raw.strip():
        raw = raw.strip()
        if raw.startswith('['):
            try:
                parsed = json.loads(raw)
                return json.dumps([str(t).strip() for t in parsed if str(t).strip()])
            except (ValueError, TypeError):
                pass
        return json.dumps([t.strip() for t in raw.split(',') if t.strip()])
    return '[]'
