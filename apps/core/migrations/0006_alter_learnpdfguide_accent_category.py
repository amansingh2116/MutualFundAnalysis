# Generated for LearnPDFGuide field length expansion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_add_is_featured_to_blog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='learnpdfguide',
            name='accent',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name='learnpdfguide',
            name='category',
            field=models.CharField(
                choices=[
                    ('chapters', 'Chapterwise Guides'),
                    ('handbook', 'Complete Handbook'),
                    ('other', 'Other Guides'),
                ],
                default='other',
                max_length=50,
            ),
        ),
    ]
