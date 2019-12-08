---
layout: default
---

{% for post in site.posts %}
<p class="post-date">{{ post.date | date: "%B %e, %Y" }}</p> [{{ post.title }}]({{ post.url }})
{% endfor %}
