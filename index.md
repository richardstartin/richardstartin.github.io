---
layout: default
---

{% for post in site.posts %}
<p class="post-date">{{ post.date | date: "%B %e, %Y" }} [{{ post.title }}]({{ post.url }})</p>
{% endfor %}
