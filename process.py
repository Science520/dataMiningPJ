import json  
import os  
import time  
import re  
import argparse  
from typing import List, Dict, Any, Set  
from urllib.parse import urlparse, quote, quote_plus  
import requests  
import PyPDF2  
import io  
import tempfile  
from pdf_url import can_access

from bs4 import BeautifulSoup  

def _on_error(msg: str):  
    """打印错误信息"""  
    print("\033[01;31m[!]\033[0;m", msg)  

def _log(msg: str):  
    """打印日志信息"""  
    print("\033[01;92m[!]\033[0;m", msg)  

def fetch_paper(input_url: str) -> list:  
    """从OpenReview会议页面获取所有论文的PDF链接"""  
    try:  
        res = requests.get(input_url)  
        res.raise_for_status()  
    except:  
        _on_error("请求错误")  
        return []  

    html_doc = res.text  
    try:  
        soup = BeautifulSoup(html_doc, 'html.parser')  
    except:  
        _on_error("HTML解析错误")  
        return []  
    
    next_data = soup.find(name="script", id="__NEXT_DATA__")  
    if next_data is None:  
        _on_error("找不到JSON脚本")  
        return []  

    try:  
        direction = json.loads(next_data.string)  
    except Exception as e:  
        _on_error("JSON解码错误: " + str(e))  
        return []  

    try:  
        tabs = direction['props']['pageProps']['componentObj']['properties']['tabs']  
        domain = direction['props']['pageProps']['componentObj']['properties']['entity']['domain']  
    except:  
        _on_error("意外的JSON格式")  
        return []  

    # 获取当前选择的标签名称  
    tab_name = re.sub(r'^.*#tab-(.*)$', r'\1', input_url)  
    tab_entry = None  
    
    for tab in tabs:  
        try:  
            n1 = re.findall(r'[a-zA-Z0-9]+', tab['name'])  
            n1 = [word.lower() for word in n1]  

            n2 = re.findall(r'[a-zA-Z0-9]+', tab_name)  
            n2 = [word.lower() for word in n2]  

            if ' '.join(n1) == ' '.join(n2):  
                tab_entry = tab  
                break  
        except:  
            continue  
    
    if tab_entry is None:  
        _on_error(f'无法找到标签 {tab_name}')  
        return []  
    
    try:  
        key = 'venue'  
        venue = tab_entry['query']['content.venue']  
    except:  
        try:  
            key = 'venueid'  
            venue = tab_entry['query']['content.' + key]  
        except:  
            _on_error("无法找到venue或venueid")  
            return []  

    # 使用urllib.parse中的quote和quote_plus  
    venue = quote(venue)  
    domain = quote_plus(domain)  
    details = quote('replyCount,presentation,writable')  
    LIMIT = 1000  
    
    resource_url = f"https://api2.openreview.net/notes?content.{key}={venue}&details={details}&domain={domain}&limit={LIMIT}&offset=0"  
    
    try:  
        res = requests.get(resource_url)  
        res.raise_for_status()  
    except:  
        _on_error("请求JSON错误")  
        return []  

    forums = []  
    try:  
        resource = json.loads(res.text)  
        count = resource['count']  
        notes = resource['notes']  

        for note in notes:  
            forums.append(note['id'])  
    except Exception as e:  
        _on_error("资源JSON解码错误")  
        return []  

    offset = LIMIT  
    while offset < count:  
        resource_url = f"https://api2.openreview.net/notes?content.{key}={venue}&details={details}&domain={domain}&limit={LIMIT}&offset={offset}"  
        try:  
            res = requests.get(resource_url)  
            res.raise_for_status()  
        except:  
            _on_error('请求失败')  
            break  

        try:  
            resource = json.loads(res.text)  
            notes = resource['notes']  

            for note in notes:  
                forums.append(note['id'])  
        except Exception as e:  
            _on_error("资源JSON解码错误")  
            break  

        offset += LIMIT  

    pdf_urls = []  
    for forum in forums:  
        pdf_urls.append(f'https://openreview.net/pdf?id={forum}')  
    
    return pdf_urls  

def extract_text_from_pdf(pdf_url: str) -> str:  
    """从URL下载PDF并提取文本内容"""  
    try:  
        response = requests.get(pdf_url)  
        response.raise_for_status()  
        
        # 使用PyPDF2提取文本  
        pdf_file = io.BytesIO(response.content)  
        reader = PyPDF2.PdfReader(pdf_file)  
        
        text = ""  
        for page_num in range(len(reader.pages)):  
            page_text = reader.pages[page_num].extract_text()  
            if page_text:  
                text += page_text + "\n"  
        
        return text  
    except Exception as e:  
        _on_error(f"PDF处理失败: {str(e)}")  
        return ""  

def extract_urls_from_text(text: str, validate_urls: bool = False) -> Dict[str, List[str]]:  
    """从文本中提取URL及其上下文"""  
    if not text:  
        return {}  
    
    # 分行处理  
    lines = text.split('\n')  
    
    # 提取URL及上下文  
    url_pattern = r"https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_+.~#?&/=]*)"  
    result = {}  
    
    # 遍历每一行  
    for i, line in enumerate(lines):  
        urls = re.findall(url_pattern, line)  
        
        for url in urls:  
            # 清理URL（移除尾部的点）  
            url = re.sub(r'^(.*?)\.*$', r'\1', url)  
            
            # 验证URL是否可访问（可选）  
            if validate_urls and not can_access(url):  
                continue  
                
            if url not in result:  
                result[url] = []  
            
            # 获取上下文(当前行及前后1行)  
            start_idx = max(0, i - 1)  
            end_idx = min(len(lines), i + 2)  
            context = "\n".join(lines[start_idx:end_idx])  
            result[url].append(context)  
    
    return result  

def is_benchmark_or_dataset_link(url: str, context: str = "") -> bool:  
    """判断URL是否是数据集或基准测试相关的链接"""  
    # 解析URL  
    parsed = urlparse(url)  
    domain = parsed.netloc.lower()  
    path = parsed.path.lower()  
    
    # 数据集相关域名和路径关键词  
    dataset_domains = {  
        'github.com': ['dataset', 'benchmark', 'data', 'corpus', 'evaluation'],  
        'huggingface.co': ['datasets'],  
        'kaggle.com': ['datasets'],  
        'paperswithcode.com': ['datasets', 'benchmarks'],  
        'tensorflow.org': ['datasets', 'data'],  
        'pytorch.org': ['data', 'datasets'],  
        'zenodo.org': [],  # 整个域名都是数据集相关  
        'figshare.com': [],  
        'data.mendeley.com': [],  
        'datadryad.org': [],  
        'dataverse.harvard.edu': [],  
        'catalog.ldc.upenn.edu': [],  
        'archive.ics.uci.edu': []  
    }  
    
    # 检查域名  
    if domain in dataset_domains:  
        if not dataset_domains[domain]:  # 空列表表示整个域名都是数据集相关  
            return True  
        for keyword in dataset_domains[domain]:  
            if keyword in path:  
                return True  
    
    # 检查路径中的关键词  
    dataset_keywords = [  
        'dataset', 'benchmark', 'corpus', 'data-download',   
        'download-data', 'data/download', 'download/data',  
        'evaluate', 'evaluation', 'metrics', 'performance',  
        'leaderboard', 'competition', 'challenge'  
    ]  
    for keyword in dataset_keywords:  
        if keyword in path:  
            return True  
    
    # 检查上下文中的关键词  
    context_lower = context.lower()  
    context_keywords = [  
        'dataset', 'data set', 'benchmark', 'corpus', 'repository',   
        'evaluation', 'metric', 'leaderboard', 'test set',  
        'training data', 'test data', 'evaluation data',  
        'repository for', 'official implementation', 'code for'  
    ]  
    for keyword in context_keywords:  
        if keyword in context_lower:  
            # 上下文中包含关键词，并且URL看起来不是博客或主页  
            if not any(x in path for x in ['blog', 'post', 'article', 'news', 'about']):  
                return True  
    
    return False  

def extract_benchmark_links_from_paper(pdf_url: str) -> Dict[str, List[str]]:  
    """从论文中提取数据集和基准测试相关链接"""  
    # 提取PDF文本  
    text = extract_text_from_pdf(pdf_url)  
    if not text:  
        return {}  
    
    # 从文本中提取所有URL及上下文  
    all_urls = extract_urls_from_text(text)  
    
    # 筛选数据集和基准测试相关链接  
    benchmark_links = {}  
    for url, contexts in all_urls.items():  
        # 对URL的所有上下文进行检查  
        relevant_contexts = []  
        for context in contexts:  
            if is_benchmark_or_dataset_link(url, context):  
                relevant_contexts.append(context)  
        
        # 如果该URL被识别为数据集/基准测试链接，保存所有相关上下文  
        if relevant_contexts:  
            benchmark_links[url] = relevant_contexts  
    
    return benchmark_links

def save_json(file_path: str, data: list) -> None:  
    """将数据以JSON格式保存到文件"""  
    with open(file_path, 'w', encoding='utf-8') as f:  
        json.dump(data, f, ensure_ascii=False, indent=2)  
    _log(f"结果已保存到 {file_path}")  

def process_conference(url: str, output_file: str, limit: int = None) -> None:  
    """处理会议论文，提取数据集和基准测试链接  
    
    Args:  
        url: OpenReview会议URL  
        output_file: 输出JSON文件路径  
        limit: 限制处理的论文数量，None表示处理全部  
    """  
    print(f"开始处理会议: {url}")  
    
    # 获取所有论文PDF链接  
    paper_urls = fetch_paper(url)  
    print(f"找到 {len(paper_urls)} 篇论文")  
    
    # 如果设置了limit，只处理指定数量的论文  
    if limit and limit > 0:  
        paper_urls = paper_urls[:limit]  
        print(f"根据限制，将只处理前 {limit} 篇论文")  
    
    # 处理每篇论文  
    all_benchmarks = []  
    
    for i, pdf_url in enumerate(paper_urls):  
        print(f"处理论文 {i+1}/{len(paper_urls)}: {pdf_url}")  
        
        try:  
            print(f"  分析论文中的数据集链接")  
            
            # 提取论文中的基准测试链接  
            benchmark_links = extract_benchmark_links_from_paper(pdf_url)  
            
            if benchmark_links:  
                paper_id = pdf_url.split('id=')[-1]  
                
                # 为每个链接创建记录  
                for url, contexts in benchmark_links.items():  
                    all_benchmarks.append({  
                        "url": url,  
                        "paper_url": pdf_url,  
                        "paper_id": paper_id,  
                        "contexts": contexts  
                    })  
                
                print(f"  找到 {len(benchmark_links)} 个数据集/基准测试链接")  
            else:  
                print("  未找到数据集/基准测试链接")  
                
        except Exception as e:  
            print(f"  处理失败: {str(e)}")  
        
        # 避免请求过于频繁  
        time.sleep(1)  
    
    # 去重处理  
    unique_urls = {}  
    for item in all_benchmarks:  
        url = item["url"]  
        if url not in unique_urls:  
            unique_urls[url] = item  
        else:  
            # 合并上下文和来源论文  
            unique_urls[url]["contexts"].extend(item["contexts"])  
            # 去除重复上下文  
            unique_urls[url]["contexts"] = list(set(unique_urls[url]["contexts"]))  
            # 添加源论文记录  
            if "source_papers" not in unique_urls[url]:  
                unique_urls[url]["source_papers"] = [unique_urls[url]["paper_id"]]  
            if item["paper_id"] not in unique_urls[url]["source_papers"]:  
                unique_urls[url]["source_papers"].append(item["paper_id"])  
    
    # 转换为列表并保存  
    result = list(unique_urls.values())  
    save_json(output_file, result)  
    print(f"处理完成。找到 {len(result)} 个唯一数据集/基准测试链接")

def main():  
    """主函数，处理命令行参数"""  
    parser = argparse.ArgumentParser(description='从OpenReview会议提取数据集和基准测试链接')  
    parser.add_argument('url', type=str, help='OpenReview会议URL')  
    parser.add_argument('-o', '--output', type=str, required=True, help='输出JSON文件路径')  
    parser.add_argument('-l', '--limit', type=int, default=10, help='限制处理的论文数量，默认为10')  
    
    args = parser.parse_args()  
    
    # 处理会议  
    process_conference(args.url, args.output, args.limit)

if __name__ == "__main__":  
    main()