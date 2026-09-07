from django.utils.feedgenerator import Atom1Feed
from django.contrib.syndication.views import Feed
from django.utils.html import strip_tags
from blog.models import blogItem as item
import datetime

class blogItemsFeed(Feed):
    title = "danlerch.ca"
    link = "/rss/"
    description = "The official RSS feed for Dan Lerch."

    def items(self):
        return item.objects.order_by("-blog_date")[:5]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.search_description

    # item_link is only needed if blogItem has no get_absolute_url method.
    def item_link(self, item):
        return item.url

class AtomSiteNewsFeed(blogItemsFeed):
    feed_type = Atom1Feed
    subtitle = item.search_description
