"""
A crawler tailored for downloading papers from https://openreview.net

Author https://github.com/Fudanyrd
"""
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

try:
    # https://stackoverflow.com/questions/17462884/is-selenium-slow-or-is-my-code-wrong
    # https://selenium-python.readthedocs.io/locating-elements.html#locating-by-xpath
    # https://selenium-python.readthedocs.io
    import selenium
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    import time
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    
    browser = None

    def selenium_load_tags(base_url: str) -> list:
        """
        Example usage:
        >>> selenium_load_tags("https://openreview.net/group?id=ICLR.cc%2F2017%2Fconference")
        ['your-consoles', 'poster-presentations', 'oral-presentations', \
         'rejected-submissions', 'invite-to-workshop-track']
        """
        # must enable -headless to run without vga
        option = webdriver.FirefoxOptions()
        option.add_argument('-headless')
        firefox = webdriver.Firefox(option)
        firefox.get(base_url)
        time.sleep(2.5)

        items = firefox.find_elements(By.CSS_SELECTOR, '.tab-content>.tab-pane.fade')
        ret = []
        for item in items:
            url = item.get_attribute('id') 
            print(url)
            if re.match(r'^[a-z0-9A-Z_\-]+$', url):
                ret.append(url)

        if len(ret) == 0:
            xpath = "//div[@id=\"notes\"]/div/div/ul/li/a"
            items = firefox.find_elements(By.XPATH, xpath)
            for item in items:
                url = item.get_attribute('href')
                if re.match(r'.*#[a-zA-Z0-9_\-]+$', url):
                    ret.append(re.sub(r'.*#([a-zA-Z0-9_\-]+)$', r'\1', url))

        firefox.quit()
        return ret
    
    def selenium_load_tags_safe(base_url: str, max_retries: int = 3):
        """
        Example usage:
        >>> selenium_load_tags("https://openreview.net/group?id=ICLR.cc%2F2017%2Fconference")
        ['poster-presentations', 'oral-presentations', ...]
        """
        for _ in range(max_retries):
            try:
                ret = selenium_load_tags(base_url) 
            except:
                continue
            return ret

        _on_error("selenium_load_tags_safe(): max retries reached.")
        return []

    def selenium_load_batch(driver, tab_id):
        """
        Load a batch of papers.
        """
        ret = []
        elem = None

        xpath = f'//div[@id=\'{tab_id}\']/div/div/ul/li|//div[@id=\'{tab_id}\']/ul/li'
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, xpath))
            )
        except Exception as e:
            _on_error("selenium_load_batch: " + str(e))
            return ret, None

        lst = driver.find_elements(By.XPATH, xpath)
        print(len(lst))

        for item in lst:
            id = item.get_attribute('data-id')
            if id:
                ret.append(id)
        
        elem = lst[0] if len(lst) else None
        if len(ret) == 0:
            xpath = f'//div[@id=\'{tab_id}\']/div/div/ul/li/div/h4/a[1]'
            lst = driver.find_elements(By.XPATH, xpath)
            elem = lst[0] if len(lst) else None
            for item in lst:
                href = item.get_attribute('href')
                if re.match(r'.*id=[a-zA-Z0-9_\-]+.*', href):
                    ret.append(re.sub(r'.*id=([a-zA-Z0-9_\-]+).*', r'\1', href))

        del lst
        return ret, elem
    

    def selenium_load_ids(base_url: str):
        global browser
        option = webdriver.FirefoxOptions()
        option.add_argument('-headless')
        firefox = webdriver.Firefox(option)
        browser = firefox
        firefox.get(base_url)

        tab_id = re.sub(r'^.*#(.*)$', r'\1', base_url)
        if tab_id.startswith('tab-'):
            tab_id = tab_id[4:]

        # ret = selenium_load_batch(firefox, tab_id)
        ret = []

        try:
            WebDriverWait(firefox, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "tabs-container"))
            )
            ul_xpath = f'//div[@id=\'{tab_id}\']/div/div/ul|//div[@id=\'{tab_id}\']/ul'
            WebDriverWait(firefox, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, ul_xpath))
            )
        except:
            print("line 139, waiterror", file=sys.stderr)
            pass

        # locate navigation button
        xpath = f'//div[@id=\'{tab_id}\']/div/div/nav/ul/li/a|//div[@id=\'{tab_id}\']/nav/ul/li/a'
        pages = firefox.find_elements(By.XPATH, xpath)
        n_pages = len(pages)
        n_invalid = 0
        for i in range(n_pages):
            if not re.match(r'[0-9]+', pages[i].text):
                n_invalid += 1
        print(n_pages, tab_id)

        if n_pages == 0:
            tup = selenium_load_batch(firefox, tab_id)
            ret += tup[0]
            firefox.quit()
            browser = None
            return ret

        click = False
        i: int = 0
        elem = None
        #for i in range(n_pages - n_invalid):
        while True:
            button = None # pages[i]

            # if 'disabled' in button.get_attribute('class'):
            #     continue
            # if 'arrow' in button.get_attribute('class'):
            #     continue
            # if not re.match(r'[0-9]+', button.text):
            #     continue

            for k in range(n_pages):
                if pages[k].text == str(i + 1):
                    button = pages[k]

            if button is None:
                break

            print(i, button.text)
            # click the button
            if click:
                # Wait until the overlay is not visible
                WebDriverWait(firefox, 10).until(
                    EC.invisibility_of_element_located((By.CLASS_NAME, "content-overlay"))
                )
                button.click()
                try:
                    WebDriverWait(firefox, 10).until(
                        EC.invisibility_of_element_located((By.CLASS_NAME, "content-overlay"))
                    )
                    if elem:
                        WebDriverWait(firefox, 10).until(
                            EC.staleness_of(elem)
                        )
                except Exception as e:
                    print(e, file=sys.stderr)
                finally:
                    del elem
                    elem = None
                # time.sleep(2.5)
            else:
                click = True

            buf, elem = selenium_load_batch(firefox, tab_id)
            ret += buf 
            del buf

            # relocate
            del button
            del pages
            pages = firefox.find_elements(By.XPATH, xpath)
            i += 1
            n_pages = len(pages)
        
        firefox.quit()
        browser = None
        return ret
    
    def selenium_load_ids_safe(base_url, max_retries=3):
        global browser
        for _ in range(max_retries):
            try:
                ret = selenium_load_ids(base_url)
            except:
                if browser:
                    browser.quit()
                    browser = None
                continue
            return ret
        
        _on_error("max retries exceeded in selenium_load_ids_safe")
        return []

    def selenium_test():
        inputs = [
            "https://openreview.net/group?id=AAAI.org/2024/Workshop/AI4ED#tab-accept-day-2-spotlight",
            "https://openreview.net/group?id=ICLR.cc%2F2017%2Fconference#poster-presentations",
            "https://openreview.net/group?id=NeurIPS.cc/2024/Conference#tab-accept-poster",
            "https://openreview.net/group?id=AAAI.org/2024",
        ]
        ans = [
            ['HkJwIypfus', 'Hqqmzn5MkZ', 'eQsALnjme9', '2vo9fAgZw3', 'REidmDpL9r'],
            None, # list too long
            None,
            []
        ]
        counts = [
                5, 183, 
                3649, 0,]
        

        assert len(inputs) == len(ans)
        
        n = len(inputs)
        for i in range(n):
            ret = selenium_load_ids_safe(inputs[i])
            a = ans[i]
            deduped = set(ret)

            assert len(deduped) == len(ret), f"duplicate id found at testcase {i}."
            if a:
                assert sorted(ans[i]) == sorted(ret), f"wrong answer at testcase {i}"
            else:
                assert len(deduped) == counts[i], f'wrong answer at testcase {i}'

except:
    def selenium_load_tags(base_url: str) -> list:
        return []

    def selenium_load_tags_safe(base_url: str) -> list:
        return []
    
    def selenium_load_ids(base_url):
        return []
    
    def selenium_load_ids_safe(base_url):
        _on_error("not implemented.\nPerhaps you forgot to install selenium?")
        return []

    print("Selenium not avaiable. Some features cannot be used.", file=sys.stderr)
    pass

EXAMPLE_INPUT = "https://openreview.net/group?id=ICLR.cc/2025/Conference#tab-accept-oral"
EXAMPLE_API_REQUEST = "https://api2.openreview.net/notes?content.venue=ICLR%202025%20Oral&details=replyCount,presentation,writable&domain=ICLR.cc/2025/Conference&limit=25&offset=0"
EXAMPLE_PDF_URL = "https://openreview.net/pdf?id=odjMSBSWRt"

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
        _on_error("OpenReviewVersionError: unexpected json format.")

        #
        # This is one of the corner case which (I assume) we should handle.
        # Generally, `selenium` is a more general handler for this, but 
        # it is surprisingly slow.
        #
        keys = selenium_load_ids_safe(input)
        ret = []

        for k in keys:
            ret.append('https//openreview.net/pdf?id=' + k)
        return ret

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
    LIMIT: int = 1000
    resource_url = f"https://api2.openreview.net/notes?content.{key}={venue}&details={details}&domain={domain}&limit={LIMIT}&offset=0"
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

    offset = LIMIT
    while offset < count:
        resource_url = f"https://api2.openreview.net/notes?content.{key}={venue}&details={details}&domain={domain}&limit={LIMIT}&offset={offset}"
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

        offset += LIMIT

    ret = []
    for forum in forums:
        ret.append(f'https://openreview.net/pdf?id={forum}')
    
    return ret

def get_venues():
    """
    :return: a list of active venues.
    """

    try:
        res = requests.get('https://api2.openreview.net/groups?id=host')
        res.raise_for_status()
        assert res.status_code == 200
    except:
        _on_error("failed to access groups?id=active_venues")
        return []

    try:
        d = json.loads(res.text)
        ret = d['groups'][0]['members']
    except:
        _on_error("failed to decode json text") 
        return []
    
    return sorted(ret) 

def venue_get_tags(venue: str):
    """
    Get the tags of a venue.

    Example usage:
    >>> venue_get_tags('AAAI.org/2024/Workshop/AI4ED')
    ['accept-day-1-oral', 'accept-day-2-spotlight', 'accept-day-1-poster', 'accept-day-2-poster']
    >>> venue_get_tags('ICLR.cc/2025/Conference')
    ['accept-oral', 'accept-spotlight', 'accept-poster', 'reject', 'withdrawn-submissions', 'desk-rejected-submissions']
    """
    url = 'https://openreview.net/group?id=' + urllib.parse.quote_plus(venue)
    try:
        res = requests.get(url)
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
        properties = direction['props']['pageProps']['componentObj']['properties']
        if 'tabs' not in properties:
            # ok, do not log this.
            return []

        tabs: list = properties['tabs']
        ret = []

        for tab in tabs:
            name = tab['name'] # maybe "Accept (day 1 poster)"
            words: list[str] = re.findall(r'[a-zA-Z0-9]+', name)
            for i in range(len(words)):
                words[i] = words[i].lower()
            ret.append('-'.join(words))

            del words
        
        del tabs
    except:
        _on_error("unexpected json format, " + url)
        return []

    return ret

def recurse_venue(venue: str, output_lst: list):
    domain = urllib.parse.quote_plus(venue)

    try:
        url = 'https://api2.openreview.net/groups?parent=' + domain
        res = requests.get(url)
    except:
        _on_error("failed to access " + url)
        return

    try:
        d = json.loads(res.text)
        count = d['count']
        if len(d['groups']):
            _ = d['groups'][0]['id']
    except:
        _on_error("failed to decode json text in " + url) 
        return

    output_lst.append(venue)
    if count == 0:
        # at leaf node,
        # eg. https://api2.openreview.net/groups?parent=AAAI.org/2024/Bridge/AI4Design
        # stop recursion
        return

    for i in range(count):
        try:
            id = d['groups'][i]['id']
        except:
            msg = f'recursion at {url}, position {i} does not have id'
            _on_error(msg)
            continue

        try:
            recurse_venue(id, output_lst)
        except:
            _on_error('possible recursion limit')
            break

    return

def possible_inputs():
    """
    :return: a list of all possible inputs given by TA.

    Example output:
    >>> possible_inputs()
    []
    """
    ret = []
    base_url = 'https://openreview.net/group?id=' 

    venues = get_venues()
    for venue in venues:
        children = []
        recurse_venue(venue, children)
        for child in children:
            #tags = venue_get_tags(child)
            tags = selenium_load_tags_safe( base_url + urllib.parse.quote_plus(child) )

            for tag in tags:
                ret.append(f'https://openreview.net/group?id={child}#tab-{tag}')
        
        del children

    del venues
    return ret

if __name__ == "__main__":
    urls = [
        # CVPR Posters
        "https://openreview.net/group?id=thecvf.com/CVPR/2025/Workshop/CVDD#tab-accept-poster",
        "https://openreview.net/group?id=thecvf.com/CVPR/2025/Workshop/MIV#tab-accept-poster",
        # NeurIPS Conference
        "https://openreview.net/group?id=NeurIPS.cc/2024/Conference#tab-accept-oral",
        "https://openreview.net/group?id=NeurIPS.cc/2024/Conference#tab-accept-spotlight",
        "https://openreview.net/group?id=NeurIPS.cc/2024/Conference#tab-accept-poster",
        "https://openreview.net/group?id=NeurIPS.cc/2024/Conference#tab-reject",
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

    try:
        print("This is not intended for execution. Press Enter to run tests.", file=sys.stderr)
        _ = input()
    except:
        print("well, bye.", file=sys.stderr)
        os._exit(0)

    # may take a few minutes to complete.
    import random
    random.seed(42)
    for url in urls:
        lst = fetch_paper(url)
        lst2 = selenium_load_ids_safe(url)
        print("[R]", url, len(lst), len(set(lst2)), file=sys.stderr)

        # randomly select a pdf to verify that the url works.
        try:
            url = random.choice(lst)
            req = requests.get(url)
            req.close()
        except:
            _on_error('failed to download from ' + url)

    # if no [!] in stderr, then OK.
