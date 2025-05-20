"""
A package that finds urls and its context from a .pdf paper.
Author https://github.com/Fudanyrd

Requirements:
poppler-utils
beautifulsoup4==4.12.2

--- 
For users, take a look at pdf_find_url() and the end of the file for how to use it.

This is already tested on the following papers:
https://doi.org/10.1145/3551349.3556958
https://arxiv.org/pdf/1909.11065
https://openreview.net/pdf?id=odjMSBSWRt

--- tl; dr

A comparison of process_pdf() and process_text():
1. The urls found by process_pdf() are always correct; but some urls by process_text() 
are broken, though I have experimented intensely to detect broken urls, see can_access().
2. process_text() find all valid urls, but process_pdf does not.
3. process_pdf() is based on `pdftohtml` and requires `bs4` library.

Hence, process_text() is recommended.

---
Notes for developers

Hopefully this will help you understand my code.

The major difficulty of process_text() is that sometimes `pdftotext` put a url 
across two different lines. Some examples of this:

[1] JAttack is available at https://github.com/EngineeringSoftware/
jattack. 

[40] Andrew Haley. 2015. How to change compilation policy to trigger C2 compilation
ASAP? https://mail.openjdk.java.net/pipermail/hotspot-compiler-dev/2015-
May/018010.html.

where the actual url should be https://github.com/EngineeringSoftware/jattack and 
https://mail.openjdk.java.net/pipermail/hotspot-compiler-dev/2015-May/018010.html, 
respectively.

A walkround to this problem is to concat two lines and try to find urls in it.
However, other times, the url is contained in a single line.

ACM ISBN 978-1-4503-9475-8/22/10...$15.00
https://doi.org/10.1145/3551349.3556958
ACM Reference Format:
...

The url `should` be https://doi.org/10.1145/3551349.3556958, not  
https://doi.org/10.1145/3551349.3556958ACM

Given such condition, both urls will be added to output of process_text(), 
so one of them is INVALID, and there's not much I can do about it.
"""

#
# Documentation: https://beautiful-soup-4.readthedocs.io/en/latest/
#
from bs4 import BeautifulSoup
import bs4
import requests
from urllib.parse import urlparse, urlunparse

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

    if parent is None:
        return ""
    return parent.text

    # expand the extraction context.
    if parent.parent:
        node = parent
        parent = node.parent

    for child in parent.children:
        if child == node:
            idx = count
        lst.append(child) 
        count += 1
    
    ret: str = ""
    for i in range(max(0, idx - d), min(len(lst), 1 + d + idx)):
        plain: str = lst[i].text
        # remove html tags, use plain text.
        if plain:
            ret += plain
            ret += ' '
    
    del lst
    return ret

def _on_error(msg: str):
    print("\033[01;31m[!]\033[0;m", msg, file=sys.stderr)

def _log(msg: str):
    print("\033[01;92m[!]\033[0;m", msg, file=sys.stderr)

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

            try:
                ctx = find_context(link)
            except Exception as e:
                ctx = ""
                _on_error("error occurred during find_context()" )
            ret[url].append( ctx.replace('\xa0', ' ') )
    
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
        # f"cat {text_file} | grep http -A 2 -B 2",
        #f"cat {text_file}",
        ["cat", text_file],
        shell=False, 
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
    backup_pattern = "(?:www\\.)?[-a-zA-Z0-9@:%._\\+~#=]{1,256}\\.[a-zA-Z0-9()]{1,6}\\/[-a-zA-Z0-9()@:%_\\+\\.~#?&=\\/]*"
    url_pattern = re.compile(url_pattern)
    backup_pattern = re.compile(backup_pattern)
    while i < len(lines):
        buf = lines[i]
        buf2 = lines[i] + (lines[i + 1] if (i + 1 < len(lines))  else '')
        m1 = re.findall(url_pattern, buf)
        m2 = re.findall(url_pattern, buf2)
        m2 = m2[ : len(m1)] if len(m1) else m2[ : 1]
        if 'http' not in buf:
            #
            # if `buf` does not contain (any part of) a url, then should
            # not add m2[0] to the result.
            #
            m2 = []
        urls = set(m1 + m2)
        ctx = '\n'.join(lines[ max(0, i - 2) : min(i + 3, len(lines)) ])

        if ('http' not in buf2) and len(urls) == 0:
            # 
            # Fixed:
            # sometimes the url does not start with http(s)! sigh :)
            # for example, this paper:
            #  https://openreview.net/pdf?id=odjMSBSWRt
            # contains the url huggingface.co/datasets/anonymous152311/darkbench
            #
            # should only try this when nothing interesting found.
            #
            del m1 
            del m2 
            del urls
            m1 = re.findall(backup_pattern, buf)
            m2 = re.findall(backup_pattern, buf2)
            m2 = m2[ : len(m1)] if len(m1) else m2[ : 1]
            urls = set (m1 + m2)

        for url in urls:
            # remove trailing dots
            # if url.endswith('.'):
                # url = url[:-1]
            url = re.sub(r'^(.*?)\.*$', r'\1', url) 
            if can_access(url):
                if url not in ret:
                    ret[url] = []
                ret[url].append(ctx)
        i += 1

        del buf
        del buf2 
        del m1 
        del m2
        del urls

    return ret

def _extend_tokens(dst: list[str], src: list[str]):
    EOS = ['.', ',', ';', '?', '!', ':']
    for token in src:
        if token[-1] in EOS:
            dst.append(token[ : -1 ])
            dst.append(token[-1])
        else:
            dst.append(token)

def _index_with_count(tokens: list, target, start: int = 0, 
                      count: int = 1, backward: bool = False):

    idx = start
    if backward:
        while idx >= 0:
            if tokens[idx] == target:
                count -= 1
                if count <= 0:
                    return idx
            idx -= 1 
        return max(0, idx)
    else:
        l = len(tokens)
        while idx < l:
            if tokens[idx] == target:
                count -= 1
                if count <= 0:
                    return idx
            idx += 1
        
        return idx

def find_dataset_in_file(text_file: str):
    """
    Find dataset names and their contexts in a text file.
    :return: a set of dataset names and their context

    Example usage:
    >>> _ = os.system('wget https://arxiv.org/pdf/1909.11065 -O paper.pdf')
    >>> _ = os.system('pdftotext -raw -nopgbrk paper.txt')
    >>> r: dict = find_dataset_in_file('paper.txt')
    >>> for dataset in r:
    ...    print(dataset)
    ...
    Cityscapes
    ADE20K
    >>> print(r['ADE20K'][0])
        into 2 , 975/500/1 , 525 images for training , validation and testing . 
        ADE20K . The ADE20K dataset [82] is used in ImageNet scene parsing chal- 
        lenge 2016 . There are 150 classes and diverse scenes with 1 , 038 image-level 
    """
    datasets = {}
    if not os.path.exists(text_file):
        _on_error("cannot find " + text_file)
        return datasets

    tokens: list[str] = []

    lines: list[str] = []
    with open(text_file, 'r', encoding='utf-8') as fobj:
        for row in fobj:
            lines.append(row.strip())
    

    prev = lines[0]
    # tokens += prev.split()
    _extend_tokens(tokens, prev.split())
    tokens.append('\n')
    for i in range(1, len(lines)):
        cur = lines[i]
        lst = cur.split()

        if len(tokens) and tokens[-1].endswith('-'):
            last = tokens[-1]
            tokens[-1] = last[ : -1 ] + lst[0]
            # tokens += lst[ 1 : ]
            _extend_tokens(tokens, lst[ 1 : ])
            tokens.append('\n')
        else:
            _extend_tokens(tokens, lst)
            tokens.append('\n')

        # advance
        prev = cur

    del prev
    del cur
    del lines

    # the name of dataset can hardly exceed 3 words.
    MAX_WORDS = 3

    # control the size of context
    BEFORE = 2
    AFTER = 2

    START_TOKENS = ["the", "our", "this", "such", ]
    # eg.
    # our coco dataset,
    # this mnist dataset,
    # the dblp dataset,
    # etc.

    for i in range(len(tokens)):
        t = tokens[i]
        if 'dataset' in t.lower():
            st = max(0, i - MAX_WORDS - 1)
            idx = st

            while idx < i:
                if tokens[idx].lower() in START_TOKENS:
                    break
                idx += 1

            if idx + 1 < i:
                name = ' '.join(tokens[ idx + 1 : i ])
                name.replace('\n', '')
                name = name.strip()
                if name not in datasets:
                    datasets[name] = []

                start = _index_with_count(tokens, '\n', start=i, count=BEFORE, backward=True)
                end = _index_with_count(tokens, '\n', start=i, count=AFTER, backward=False)
                print(start, end)
                datasets[name].append(' '.join(tokens[ start : end ]))

    del tokens
    return datasets

def pdf_find_url(pdf_file: str) -> dict:
    """
    Combine the advantages of both process_text and process_pdf, also
    deduplicate the output of them.

    Example Usage:
    >>> pdf_find_url ('paper.pdf')
    """
    if not pdf_file.endswith('.pdf'):
        _on_error(pdf_file + " does not seem to be a .pdf!")
        return {}
    if not os.path.exists(pdf_file):
        _on_error("pdf file " + pdf_file + " does not present!")
        return {}

    r1 = process_pdf(pdf_file)

    try:
        res = subprocess.run(['pdftotext', '-raw', '-nopgbrk', pdf_file])
        if res.returncode != 0:
            raise RuntimeError("pdftotext failed.")
        text_file = re.sub(r'\.pdf$', r'.txt', pdf_file)
        assert os.path.exists(text_file)
        r2 = process_text(text_file)
    except:
        _on_error("pdftotext failed.")
        r2 = {}
    
    ret = {}
    def normalize_url(url: str) -> str:
        #
        # FIXME: should we even do this?
        #
        parsed = urlparse(url)
        # Remove trailing slash from the path if present
        normalized_path = parsed.path.rstrip('/')
        # Reconstruct the URL without trailing slash
        return urlunparse(parsed._replace(path=normalized_path))
    
    ret = {}
    _log(f"len(r1) = {len(r1)}, len(r2) = {len(r2)}")
    for r in [r1, r2]:
        for k in r:
            if k not in ret:
                ret[k] = []
            ret[k] += r[k]
    
    del r1
    del r2
    try:
        #
        # fixed: remove temporary file.
        #
        text_file = re.sub(r'(.*)\.pdf$', r'\1.txt', pdf_file)
        html_file = re.sub(r'(.*)\.pdf$', r'\1.html', pdf_file)
        _ = subprocess.run(
            ['rm', '-f', text_file, html_file])
    except:
        pass
    return ret

if __name__ == "__main__":
    for fname in sys.argv[1:]:
        ret = pdf_find_url(fname)
        print(len(ret), file=sys.stderr)
        for k in ret:
            print('--->', len(ret[k]), k)
            print(ret[k][0])
