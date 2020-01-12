---
layout: default
---

{% for post in site.posts %}	
{{post.date | date_to_string }} [{{ post.title }}]({{ post.url}}) 
  {% for tag in post.tags %}
    {% capture tag_name %}{{ tag }}{% endcapture %}
     [{{ tag_name }}](/tags/{{ tag_name }})
  {% endfor %}	
{% endfor %}


