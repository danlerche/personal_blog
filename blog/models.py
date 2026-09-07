from django.db import models
from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel
import datetime
from django.db.models import Count
from django.db.models.functions import ExtractYear
from wagtail.contrib.routable_page.models import RoutablePageMixin, path
from wagtail.fields import StreamField, RichTextField
from wagtail import blocks
from wagtail.blocks import CharBlock, BlockQuoteBlock
from wagtail.search import index
from wagtail.images.blocks import ImageChooserBlock

class blogIndexPage(Page):
	intro = RichTextField(blank=True)
	def get_context(self, request, *args, **kwargs):
		#get the year value from the url
	    year = request.GET.get('year')


	    # Call the parent method to get the base context
	    context = super().get_context(request)
	   
	    # Query blog items
	    blog_items = blogItem.objects.all().live().order_by('-blog_date')

	    # Filter blog items by year if 'year' is specified
	    if year:
	        blog_items = blog_items.live().filter(blog_date__year=year)

	    # Get the count of blog posts grouped by year
	    blog_count_by_year = (
	        blogItem.objects.live()
	        .annotate(year=ExtractYear('blog_date'))
	        .values('year')
	        .annotate(count=Count('id'))
	        .order_by('-year')
	    )

	    # Add the data to the context
	    context['blog_items'] = blog_items
	    context['blog_count_by_year'] = blog_count_by_year
	    context['selected_year'] = year 
	    context['url_value'] = request.GET.get('url_value', year)

	    return context

	search_fields = Page.search_fields + [
		index.SearchField('intro'),
	]
	content_panels = Page.content_panels + [
		FieldPanel('intro'),
	]

class blogItem(Page):
	blog_date = models.DateField(default=datetime.date.today)
	blog_image = models.ForeignKey('wagtailimages.Image', blank=False, null=True, help_text="upload an image for the bio", on_delete=models.SET_NULL,related_name='+')
	blog_teaser = models.TextField(null=True, blank=True, max_length=400, help_text="Optional blog teaser. If null the first sentence of the post will be used.")
	content = StreamField([
		('quote_block', blocks.StructBlock([
			('quote', BlockQuoteBlock(required=True, help_text="Enter the text you'd like to appear in quotation marks")),
			('attribution', blocks.CharBlock(required=False, help_text="attribute the quote to someone")),
			], icon='openquote')),
		('paragraph', blocks.RichTextBlock()),
		('image', ImageChooserBlock()),
		('code_snippet', blocks.CharBlock()),
		], use_json_field=True, blank=True)

	def save(self, *args, **kwargs):
        # Explicitly use the modern super() without arguments
		return super().save(*args, **kwargs)
		
	content_panels = Page.content_panels + [
        FieldPanel('blog_date'),
		FieldPanel('blog_image'),
		FieldPanel('blog_teaser'),
		FieldPanel('content'),
	]
