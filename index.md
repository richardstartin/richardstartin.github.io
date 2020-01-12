---
layout: default
---

{% for post in site.posts %}	
{{post.date | date_to_string }} [{{ post.title }}]({{ post.url}}) 
  {% for tag in page.tags %}
    {% capture tag_name %}{{ tag }}{% endcapture %}
    <div class="tag">[{{ tag_name }}](/tag/{{ tag_name }})</div>
  {% endfor %}	
{% endfor %}


