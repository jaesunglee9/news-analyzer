from django.urls import path
from .views import NewsArticleListView

urlpatterns = [
    path('articles/', NewsArticleListView.as_view(), name='newsarticle-list'),
]