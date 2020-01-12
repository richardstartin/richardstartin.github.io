---
layout: default
---

{% for post in site.posts %}	
{{post.date | date_to_string }} [{{ post.title }}]({{ post.url}}) {% for tag in post.tags %}[{{ tag_name }}](/tags/{{ tag }}){% endfor %}	
{% endfor %}


