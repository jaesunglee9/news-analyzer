from django.db import models

# Create your models here.
class NewsArticle(models.Model):
    article_company = models.CharField(max_length=50) # e.g., 'KBS', 'MBC', 'SBS'
    article_date = models.DateField()
    article_order = models.IntegerField(default=0)
    article_title = models.TextField(default='')
    article_url = models.CharField(max_length=100, default='')
    article_script = models.TextField()
    scraped_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.company} News - {self.article_date}"

class AnalysisResult(models.Model):
    article = models.OneToOneField(NewsArticle, on_delete=models.CASCADE, related_name='analysis')
    
    headline_analysis = models.JSONField(
        help_text="Analysis of the main headline story, its framing, and context."
    )

    # Stores the overall summary paragraph from the LLM
    editorial_critique = models.TextField(
        help_text="The LLM's overall critique of the broadcast's editorial choices."
    )

    # Stores the {'exclusives_claimed': [...], 'potential_omissions': [...]} object
    notable_elements = models.JSONField(
        help_text="Lists any claimed exclusives or noteworthy omissions."
    )

    # Good practice to have timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Analysis for {self.article.article_title}"
