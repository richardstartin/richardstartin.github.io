---
layout: default
---

{% for post in site.posts %}
<div class="post-pointer"><h4 class="post-date">{{ post.date | date: "%B %e, %Y" }}</h4><a href="{{ post.url}}">{{ post.title }}</a></div>
{% endfor %}
