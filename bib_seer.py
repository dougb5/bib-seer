#!/usr/bin/python3

"""
This script takes a BibTeX file and finds other papers that cite one or
more of the entries in it.  In order to scrape Google Scholar, it requires
a SerpAPI (https://serpapi.com/) API key, which it reads from the
SERP_API_KEY environment variable.

Usage:    ./bib_seer.py <bibtex_file>
"""

from collections import defaultdict
import json
import os
import re
import sys
import urllib.parse
import urllib.request

import pybtex.database

SERP_API_KEY = os.getenv("SERP_API_KEY")
SERP_API_URL = "https://serpapi.com/search"

def get_cited_by(paper):
    """Given a paper object returned by the SerpAPI, return its "cited_by" section, or {}."""
    return paper.get("inline_links", {}).get("cited_by", {})

def norm_title(title):
    """Normalize a title string for deduplication."""
    return re.sub('[^0-9a-z]+', "", title.lower())

def get_titles_from_bibtex(filename):
    """Extract the list of paper titles from a BibTeX file."""
    with open(filename) as fs:
        bibtex_content = fs.read()
        bt = pybtex.database.parse_string(bibtex_content, bib_format="bibtex")
        return [bt.entries[entry].fields['title'] for entry in bt.entries if
                'title' in bt.entries[entry].fields]

def find_citers_from_titles(titles):
    """Given a list of paper titles, search for where they're cited and return
    a list of papers that cite any of them."""

    all_citers = defaultdict(lambda: (0, None))    # link -> (count, paper_obj)

    for title in titles[:100000]:
        api_params = {"api_key": SERP_API_KEY,
                      "engine": "google_scholar",
                      "q": "\"" + title + "\""}
        api_url = SERP_API_URL + "?" + urllib.parse.urlencode(api_params)
        with urllib.request.urlopen(api_url) as r:
            res = json.loads(r.read().decode("utf-8"))
            if "organic_results" in res and len(res["organic_results"]) > 0:
                first_result = res["organic_results"][0]
                if get_cited_by(first_result):
                    cited_by_link = get_cited_by(first_result)["serpapi_scholar_link"]
                    # Remove q, add api_key
                    cited_by_link = re.sub("q=.*", "", cited_by_link) + "&api_key=" + SERP_API_KEY
                    # Fetch citers, accumulate count for each unique citer seen
                    print(cited_by_link)
                    with urllib.request.urlopen(cited_by_link) as r2:
                        cite_res = json.loads(r2.read().decode("utf-8"))
                        if "organic_results" in cite_res:
                            for res2 in cite_res["organic_results"]:
                                if "link" in res2:
                                    paper_link = res2["link"]
                                else:
                                    paper_link = "No link found (id: %s)" % (res2["result_id"])
                                all_citers[paper_link] = (all_citers[paper_link][0] + 1, res2)
    # Sort by bib hit count first, then by num. total citations (descending)
    all_citers_list = list(all_citers.items())
    all_citers_list.sort(key=lambda x: (
        1e6 * x[1][0] + (get_cited_by(x[1][1]).get("total") or 0)), reverse=True)
    return all_citers_list


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:  %s <bibtex_file>" % (sys.argv[0]))
        sys.exit()

    titles = get_titles_from_bibtex(sys.argv[1])
    norm_titles = {norm_title(t) for t in titles}
    all_citers_list = find_citers_from_titles(titles)

    # Print list as TSV
    print("\t".join(["Num bib articles cited",
                     "Num citations received",
                     "Link",
                     "Title"]))
    for (link, (count, paper_info)) in all_citers_list:
        title = paper_info.get("title", "")
        if norm_title(title) not in norm_titles:
            print("%d\t%d\t%s\t%s" % (count,
                                      get_cited_by(paper_info).get("total") or 0,
                                      link,
                                      title))
