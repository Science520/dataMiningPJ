
from bs4 import BeautifulSoup
import bs4

import re
import html
import subprocess
import os
import sys
import requests
import json
import urllib.parse

EXAMPLE_INPUT = "https://openreview.net/group?id=ICLR.cc/2025/Conference#tab-accept-oral"
EXAMPLE_API_REQUEST = "https://api2.openreview.net/notes?content.venue=ICLR%202025%20Oral&details=replyCount,presentation,writable&domain=ICLR.cc/2025/Conference&limit=25&offset=0"

def _on_error(msg: str):
    print("\033[01;31m[!]\033[0;m", msg, file=sys.stderr)

def fetch_paper(input: str) -> list:
    """
    :param input: input url as specified by project doc
    :returns: url to .pdf papers.

    Example Usage:
    >>> fetch_paper(EXAMPLE_INPUT)
    ["https://openreview.net/pdf?id=odjMSBSWRt", ...]
    """
    try:
        res = requests.get(input)
        res.raise_for_status()
        if res.status_code != 200:
            raise RuntimeError("status code is not 200")
    except:
        _on_error("request error")
        return []

    html_doc = res.text
    try:
        soup = BeautifulSoup(html_doc, 'html.parser')
    except:
        _on_error("html parse error")
        return []
    
    next_data = soup.find(name="script", id="__NEXT_DATA__")
    if next_data is None:
        _on_error("failed to find json script")
        return []

    try:
        direction = json.loads(next_data.string)
    except Exception as e:
        _on_error("json encode: " + str(e))
        return []

    try:
        tabs: list = direction['props']['pageProps']['componentObj']['properties']['tabs']
        domain: str = direction['props']['pageProps']['componentObj']['properties']['entity']['domain']

        for tab in tabs:
            _ = tab['name']
    except:
        _on_error("unexpected json format.")
        return []

    url2name = {
        # FIXME: add all possibilities
        'accept-oral': "Accept (Oral)",
        'accept-spotlight': "Accept (Spotlight)",
        'accept-poster': 'Accept (Poster)',
        'accept-day-1-poster': 'Accept (day 1 poster)',
        'reject': 'Reject',
        'withdrawn-submissions': 'Withdrawn Submissions',
        'desk-rejected-submissions': 'Desk Rejected Submissions',
        # ...
        # it is quite unlikely to enumerate all possibilies.
        # use blur matching instead.
    }
    tab_name  = re.sub(r'^.*#tab-(.*)$', r'\1', input)
    tab_entry = None
    for tab in tabs:
        try:
            n1 = re.findall(r'[a-zA-Z0-9]+', tab['name'])
            for i in range(len(n1)):
                n1[i] = n1[i].lower()

            n2 = re.findall(r'[a-zA-Z0-9]+', tab_name)
            for i in range(len(n2)):
                n2[i] = n2[i].lower()

            if ' '.join(n1) == ' '.join(n2):
                tab_entry = tab
                break
        except:
            tab_entry = None
            break
    
    if tab_entry is None:
        _on_error('cannot find tab entry ' + tab_name)
        return []
    
    try:
        key = 'venue'
        venue = tab_entry['query']['content.venue']
    except:
        _on_error("cannot find venue. ")
        try:
            key = 'venueid'
            venue = tab_entry['query']['content.' + key]
        except:
            _on_error("cannot find venueid either. abort")
            return []

    venue = urllib.parse.quote(venue)
    domain = urllib.parse.quote_plus(domain)
    details = urllib.parse.quote('replyCount,presentation,writable')
    resource_url = f"https://api2.openreview.net/notes?content.{key}={venue}&details={details}&domain={domain}&limit=250&offset=0"
    # print(resource_url, file=sys.stderr)

    try:
        header = {
            "Accept": "application/json,text/*;q=0.99",}
        res = requests.get(resource_url)
        res.raise_for_status()
        if res.status_code != 200:
            raise RuntimeError("status code is not 200")
    except:
        print(resource_url, file=sys.stderr)
        _on_error("requesting json error")
        return []

    forums = []
    try:
        resource: dict = json.loads(res.text)
        count: int = resource['count']
        notes: list = resource['notes']

        for note in notes:
            forums.append(note['id'])
    except Exception as e:
        print(res.text, file=sys.stderr)
        _on_error("resource json decode error")
        return []

    offset = 250
    while offset < count:
        resource_url = f"https://api2.openreview.net/notes?content.{key}={venue}&details={details}&domain={domain}&limit=250&offset={offset}"
        try:
            res = requests.get(resource_url)
            res.raise_for_status()
            if res.status_code != 200:
                raise RuntimeError("status code is not 200")
        except:
            _on_error('request failure')
            break

        try:
            resource: dict = json.loads(res.text)
            _: int = resource['count']
            notes: list = resource['notes']

            for note in notes:
                forums.append(note['id'])
        except Exception as e:
            print(res.text, file=sys.stderr)
            _on_error("resource json decode error")
            break

        offset += 250

    ret = []
    for forum in forums:
        ret.append(f'https://openreview.net/pdf?id={forum}')
    
    return ret

if __name__ == "__main__":
    urls = [
        # AAAI Symposium
        "https://openreview.net/group?id=AAAI.org/2024/Spring_Symposium_Series/Clinical_FMs#tab-accept",
        # AAAI Workshop
        "https://openreview.net/group?id=AAAI.org/2024/Workshop/AI4ED#tab-accept-day-1-oral",
        "https://openreview.net/group?id=AAAI.org/2024/Workshop/AI4ED#tab-accept-day-2-spotlight",
        "https://openreview.net/group?id=AAAI.org/2024/Workshop/AI4ED#tab-accept-day-1-poster",
        "https://openreview.net/group?id=AAAI.org/2024/Workshop/AI4ED#tab-accept-day-2-poster",
        # ICLR Oral/Poster
        EXAMPLE_INPUT,
        "https://openreview.net/group?id=ICLR.cc/2025/Conference#tab-accept-spotlight",
        "https://openreview.net/group?id=ICLR.cc/2025/Conference#tab-accept-poster",
        "https://openreview.net/group?id=ICLR.cc/2025/Conference#tab-reject",
        "https://openreview.net/group?id=ICLR.cc/2025/Conference#tab-withdrawn-submissions",
        "https://openreview.net/group?id=ICLR.cc/2025/Conference#tab-desk-rejected-submissions",
    ]

    # may take a few minutes to complete.
    for url in urls:
        lst = fetch_paper(url)
        print(url, len(lst), file=sys.stderr)

    # if no [!] in stderr, then OK.
