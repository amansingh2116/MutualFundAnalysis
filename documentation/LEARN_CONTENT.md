# Learn Content Workflow

The Learn section is a file-backed content area for educational PDFs, project reports, markdown blogs, and the current placeholder Community page.

## User-Facing Pages

- `Learn -> Resources` lists PDF guides and blog articles.
- `Learn -> Community` is currently a static/dummy discussion page. It is intentionally ready for a later Disqus or custom community integration.
- Blog detail pages render markdown from `Resources/Blogs` and serve local chart/thumbnail images safely from `Resources`.
- PDF cards open local PDFs from `Resources/PDF Guides/pdfs`.

## Blog Posts

Add markdown files directly under:

```text
Resources/Blogs/
```

Each blog should start with front matter:

```markdown
---
title: "My Blog Title"
description: "Short summary shown on the Resources page."
slug: "my-blog-title"
thumbnail: "images/my_blog/cover.png"
read_time: "6 min read"
order: 20
published: true
---
```

Notes:

- `thumbnail` is relative to the markdown file location.
- Blog images can use normal markdown image syntax, for example `![Chart](images/my_blog/chart.png)`.
- Supported local image types are PNG, JPG, JPEG, WEBP, and GIF.
- `order` controls card ordering on the Resources page.
- `published: false` hides the blog when synced.

## PDF Guides

Place PDF files under:

```text
Resources/PDF Guides/pdfs/
```

Add or update metadata in:

```text
Resources/PDF Guides/guides.json
```

Example entry:

```json
{
  "file": "pdfs/example.pdf",
  "title": "Example Guide",
  "description": "A short description shown on the Resources page.",
  "slug": "example-guide",
  "accent": "Guide",
  "cover": "covers/example.jpg",
  "order": 90,
  "published": true
}
```

Notes:

- `file` is relative to `Resources/PDF Guides`.
- `cover` is optional and also relative to `Resources/PDF Guides`.
- If no cover is provided, the UI shows a generated PDF-style card.
- `accent` is the short label shown on generated PDF cards.

## Sync Command

After adding or changing Learn content, run:

```bash
python manage.py sync_content
```

The command upserts:

- `LearnPDFGuide` records from `Resources/PDF Guides/guides.json` and PDFs in `pdfs/`.
- `LearnBlogPost` records from markdown front matter in `Resources/Blogs/*.md`.

If the database is temporarily unavailable in local development, the Resources and blog views fall back to scanning the files directly so the Learn section remains viewable. The database-backed sync is still the intended production/admin workflow.

## Admin Editing

Synced records are available in Django admin:

- Core -> Learn PDF Guides
- Core -> Learn Blog Posts

Admin edits can adjust title, description, order, and publish status. Running `sync_content` again will refresh fields from the source files/metadata.
