from django.shortcuts import render
from rest_framework import generics
from .models import NewsArticle
from .serializers import NewsArticleSerializer

# Create your views here.

class NewsArticleListView(generics.ListAPIView):
    """
    This view provides a list of all scraped news articles.
    """
    queryset = NewsArticle.objects.all().order_by('-article_date')
    serializer_class = NewsArticleSerializer

