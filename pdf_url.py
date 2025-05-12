"""
A package that finds urls and its context from a .pdf paper.
Author https://github.com/Fudanyrd

Requirements:
poppler-utils
beautifulsoup4==4.12.2

A comparison of process_pdf() and process_text():
1. The urls found by process_pdf() are always correct; but some urls by process_text() 
are broken, though I have experimented intensely to detect broken urls, see can_access().
2. process_text() find all valid urls, but process_pdf does not.
3. process_pdf() is based on `pdftohtml` and requires `bs4` library.

Hence, process_text() is recommended.
"""

#
# Documentation: https://beautiful-soup-4.readthedocs.io/en/latest/
#
from bs4 import BeautifulSoup
import bs4
import requests

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

def can_access(url: str):
    #
    # FIXME: because of the "Great Wall", access to github is simply not possible.
    #  Use very simple rules for now.

    # for example,
    # https://mail.openjdk.java.net/pipermail/hotspot-compiler-dev/2015-
    # https://llvm.org/docs/
    # are (probably) incomplete;
    # 
    if url.endswith('-'):
        return False
    
    # https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2022-213058https://www.oracle.com/security-alerts/cpujan2022.html
    # is probably broken.
    res = re.findall(r'https?://', url)
    if len(res) > 1:
        return False

    return True

    # directly accessing the url via internet will be good :)

    try:
        res = requests.get(url, timeout=5.0)
        res.raise_for_status()
        assert res.status_code == 200
    except:
        return False
    return True

def process_text(text_file: str):
    """
    :param text_file: output file name of `pdftotext`
    :return: all urls and their contexts in the text file.

    NOTE: some urls may be invalid
    Example Usage:
    >>> import os
    >>> assert os.system('pdftotext -nopgbrk -raw paper.pdf') == 0
    >>> process_text('paper.txt')
    """
    if not os.path.exists(text_file):
        _on_error("cannot find " + text_file)
        return {}
    
    res = subprocess.run(
        f"cat {text_file} | grep http -A 2 -B 2",
        shell=True, 
        capture_output=True)
    
    if res.returncode != 0:
        _on_error("grep failed.")
        return {}

    ret = {}
    output = res.stdout.decode()
    lines = output.split('\n')
    for i in range(len(lines)):
        lines[i] = lines[i].strip()
	
    i = 0;
    url_pattern = "https?:\\/\\/(?:www\\.)?[-a-zA-Z0-9@:%._\\+~#=]{1,256}\\.[a-zA-Z0-9()]{1,6}\\b(?:[-a-zA-Z0-9()@:%_\\+.~#?&\\/=]*)"
    while i < len(lines):
        buf = lines[i]
        buf2 = lines[i] + (lines[i + 1] if (i + 1 < len(lines))  else '')
        m1 = re.findall(url_pattern, buf)
        m2 = re.findall(url_pattern, buf2)
        m2 = m2[ : len(m1)] if len(m1) else m2[ : 1]
        urls = set(m1 + m2)
        ctx = '\n'.join(lines[ max(0, i - 2) : min(i + 3, len(lines)) ])

        for url in urls:
            if url.endswith('.'):
                url = url[:-1]
            if can_access(url):
                if url not in ret:
                    ret[url] = []
                ret[url].append(ctx)
        i += 1

    return ret

if __name__ == "__main__":
    for fname in sys.argv[1:]:
        ret = process_pdf(fname)
        print(len(ret), file=sys.stderr)
        print(ret.keys(), file=sys.stderr)
