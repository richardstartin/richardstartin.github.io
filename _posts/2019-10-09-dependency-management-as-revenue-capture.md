---
title: "Dependency Management as Revenue Capture"
layout: post
date: 2019-10-09
author: "Richard Startin"
---

I think the state of enterprise reliance on open source libraries is slightly crazy.
It's crazy because it's so precarious; so reliant on continued access, gratis, to strangers' time. 
My concern isn't self serving: I haven't done much open source development and have only ever done so out of personal interest or for direct benefit.
I don't even feel particularly strongly for open source contributors: they made something useful available for free, derived satisfaction from doing so, and may even have destroyed commercial offerings paying people's salaries.
Indeed, some open source libraries are so good that they advertise their developer's skill; individuals may even benefit indirectly by commanding higher day rates, salary, or securing consultancy assignments.

The problem with open source libraries is that companies start building hard dependencies on their continued, unfunded, maintenance.
On the one hand, that's their prerogative; the libraries are available free of charge and they can either use them or not.
On the other hand, enterprises use these libraries because it means they don't need to build the same functionality themselves, which sets a value on the continued existence of the library.
The upper bound on this value is the cost of hiring and keeping hold of developers capable of developing and maintaining an equivalent library.
Instead of setting such a price and paying it, they become dependent on some unpaid stranger somewhere not dying or losing interest. 
All of this happens without much budgetary acknowledgement or awareness within the enterprise.
Wouldn't it just be morally right _and_ strategically sane to ensure funding exists for the libraries they use?

Ensuring that developers of widely used open source libraries get compensated ameliorates the risk inherent in depending them, but how do developers accept payment?
I know of cases where developers of widely used libraries have attempted to retrospectively monetise their projects, and I'm not sure they succeed.
Of course, it's a hard sell to provide something for free, and then try to secure payment afterwards: it used to be free. 
These libraries go unfunded, at least partially, because it's very difficult to actually make the payment.

There are emerging mechanisms for paying maintainers such as GitHub sponsorship, but this mechanism targets developers, not businesses.
If GitHub sponsorship proves to be a low quality stream of revenue, I suppose there _is_ a sense of entitlement in some developers, but focusing on this misses the point. 
GitHub sponsorship targets individuals, some of whom are just bad people who won't pay anyway, but others are people who recognise the need to secure the futures of libraries, but may not control budgets.
People within enterprises aware of initiatives like GitHub sponsorship may not be authorised to make payments on the behalf of their businesses; there may be no defined process for doing so.

So if enterprises _don't even know_ how dependent they are on your software, don't know who you are, have no idea how to pay you, and have various process obstacles to actually making payments to secure the future of your brilliant library, how do you get funded?
I think the fundamental problem is with the distribution mechanism - in the JVM ecosystem, Maven Central - in that it is, itself, entirely free to use.
I've often wondered why Maven Central exists, what the people who keep it going get paid, how I can send them some cash to make it work better, but also why I should send them any cash when so many others don't.
As an occasional uploader to Maven, I have found it less than entirely reliable (but it's difficult to comprehend the scale of the service they provide, for free).
Every enterprise I have ever worked at operates some kind of cache on top of Maven Central (some with white-listing) - this is the access point.

What if enterprises were forced to actually pay for the open source software they download, and this needed to be included in product budgets?
Capturing revenue at the distribution point for open source libraries creates potential for a market and competition!
Dependency manager services could compete on quality of service, but also on content, that is, which libraries are available.
In order to secure quality content, and therefore better chances of being securing business, dependency managers could _pay_ library authors to release their libraries at their venue.
Paying authors a royalty per download (by a paying customer) would mean that those authors of the "bedrock" libraries would actually get compensated according to demand.

Doesn't it sound terrible that all of a sudden you would have to pay to download software, even for educational or recreational purposes? 
Wouldn't this kill the impetus for creation of open source?
Dependency managers would be incentivised to encourage open source development because ultimately more libraries means more content; it would be in their interests to provide community access accounts for individuals.


