from rest_framework import serializers
from .models import NewsArticle

class NewsArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsArticle
        # Specify the fields from the model you want to include in the API output
        fields = [
            'id',
            'broadcaster',
            'article_date',
            'article_title', 
            'article_url',
            'raw_script',
            'scraped_at'
            ]
        