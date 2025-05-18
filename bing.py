"""
Search anything via https://bing.com, but you will probably want to search 
for the homepage of a dataset or a benchmark.
"""
import requests
import os
import base64
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.print_page_options import PrintOptions

import time
query = 'mnist dataset'
def bing_search(query: str) -> list:
    """
    If you can find the dataset name with pdf_url.find_dataset_in_file(),
    then I can search on bing.com for its homepage. 

    Example usage
    >>> from bing import bing_search
    >>> bing_search('pascal context dataset -csdn')
    ["https://cs.stanford.edu/~roozbeh/pascal-context/", ...]
    >>> bing_search('ade20k dataset -csdn')
    ["https://github.com/CSAILVision/ADE20K", ...]
    """
    option = webdriver.FirefoxOptions()
    option.add_argument('-headless')
    firefox = webdriver.Firefox(option)
    input_url = 'https://www.bing.com/'
    firefox.get(input_url)

    box = firefox.find_element(By.ID, "sb_form_q")
    box.send_keys(query)
    box.send_keys(Keys.ENTER)
    time.sleep(3.0)

    urls = set()
    ret = []
    elements = firefox.find_elements(By.TAG_NAME, "a")

    for elem in elements:
        url: str = (elem.get_attribute('href'))
        if url and not url.startswith('https://cn.bing.com') \
            and not url.startswith('javascript'):
            if url not in urls:
                ret.append(url)
            urls.add(url)

    del urls
    time.sleep(1)
    firefox.quit()

    return ret

if __name__ == "__main__":
    q = input()

    print("searching " + q)
    ret = bing_search(q)
    for r in ret:
        print(r)
