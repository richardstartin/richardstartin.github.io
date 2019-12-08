---
layout: default
---

{% for post in site.posts %}
<div class="post-pointer"><p class="post-date">{{ post.date | date: "%B %e, %Y" }}</p><a href="{{ post.url}}">{{ post.title }}</a></div>
{% endfor %}
