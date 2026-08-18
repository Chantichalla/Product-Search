plan : after extraction of users product details the scrape pipiline start -> the ddgs instance should go for 5-7 divided parallel searches in different engines we have (google/bing/brave/DDG) ->product url filtering -> deduplication of links ->send to crawl4AI instance ->the scraping techinques/strategy/methods from(hard_truth_pipeline_comaprison.md.resolved) we followed inside of concurrency also add any from single_product if needed -> now we will get the fit_markdown or raw_markdown data from crawl4AI instance , then pass it directly to the next stage/Advisor LLM .


 for feature enquiry : we need to get the information from the cache of the product details extracted first , then if we need more details of that then we use either tavily or concurrency to search the web for articles/blog's/posts about that feature then we give response of that to the advisor, this will be the feature query type flow.

 TO-DO :
 for the user single url extraction do not use the whole v3 of cascade scraping , it is a waste of time . Because the users gives an e-commerce link the it will have JS heavy page, so we need to use the crawl4AI directly.