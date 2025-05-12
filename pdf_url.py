"""
A package that finds urls and its context from a .pdf paper.

Requirements:
poppler-utils
beautifulsoup4==4.12.2
"""

#
# Documentation: https://beautiful-soup-4.readthedocs.io/en/latest/
#
from bs4 import BeautifulSoup
import bs4

import re
import html
import subprocess
import os
import sys

def is_url(line: str) -> bool:
    url_pattern = "https?:\\/\\/(?:www\\.)?[-a-zA-Z0-9@:%._\\+~#=]{1,256}\\.[a-zA-Z0-9()]{1,6}\\b(?:[-a-zA-Z0-9()@:%_\\+.~#?&\\/=]*)"
    return re.match(url_pattern, line) is not None

def find_context(node, d: int = 4):
    parent = node.parent
    idx = None
    count = 0
    lst = []

    for child in parent.children:
        if child == node:
            idx = count
        lst.append(child) 
        count += 1
    
    ret: str = ""
    for i in range(max(0, idx - d), min(len(lst), 1 + d + idx)):
        ret += str(lst[i])
    
    del lst
    return ret

def _on_error(msg: str):
    print("\033[01;31m[!]\033[0;m", msg, file=sys.stderr)

def find_node_with_url(node, lst: list):
    has_children = False
    try:
        for child in node.children:
            has_children = True
            find_node_with_url(child, lst)
    except:
        has_children = False
    
    if has_children:
        return
    
    if node.name == "a":
        return

    url_pattern = "https?:\\/\\/(?:www\\.)?[-a-zA-Z0-9@:%._\\+~#=]{1,256}\\.[a-zA-Z0-9()]{1,6}\\b(?:[-a-zA-Z0-9()@:%_\\+.~#?&\\/=]*)"
    if re.findall(url_pattern, str(node)):
        lst.append(node)


def process_pdf(pdf_filename: str) -> dict:
    """
    :param pdf_filename: the pdf file to process.
    :return: a dict whose keys are urls and values are list of the context(s) of the key.
    """
    res = subprocess.run(
        ["pdftohtml", 
         "-i",      # ignore images
         "-hidden", # force hidden text extraction
         "-stdout", # print to stdout
         "-s",
         pdf_filename],
        capture_output=True)
    
    if res.returncode != 0:
        _on_error("pdftohtml failed.")
        print(res.stderr.decode(), file=sys.stderr)

    try:
        html_doc = res.stdout.decode()
        html_doc = html.unescape(html_doc)
    except:
        _on_error("html doc decode error.")
        return {}

    try:
        soup = BeautifulSoup(html_doc, 'html.parser')
        probable = soup.find_all('a')
    except Exception as e:
        _on_error(str(e))
        return {}
    

    ret = {}

    for link in probable:
        url = link.get('href')
        if url is not None and is_url(url):
            url = str(url)
            if url not in ret.keys():
                ret[url] = []
            
            ret[url].append( find_context(link) )
    
    nodes = []
    try:
        find_node_with_url(soup, nodes)
    except:
        _on_error("find_node_with_url() failed.")
        nodes = []
    
    del html_doc
    del probable
    del soup 
    return ret

if __name__ == "__main__":
    for fname in sys.argv[1:]:
        ret = process_pdf(fname)
        print(len(ret), file=sys.stderr)
        print(ret.keys(), file=sys.stderr)
