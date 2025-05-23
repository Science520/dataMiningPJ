import requests  
from bs4 import BeautifulSoup  
import json  
import re  

def debug_fetch_paper(conference_url: str):  
    """调试版本的fetch_paper函数"""  
    try:  
        print(f"正在访问: {conference_url}")  
        response = requests.get(conference_url)  
        response.raise_for_status()  
        
        print(f"响应状态码: {response.status_code}")  
        print(f"响应长度: {len(response.text)}")  
        
        # 保存HTML到文件进行检查  
        with open('debug_page.html', 'w', encoding='utf-8') as f:  
            f.write(response.text)  
        print("HTML已保存到 debug_page.html")  
        
        soup = BeautifulSoup(response.text, 'html.parser')  
        
        # 查找所有脚本标签  
        scripts = soup.find_all('script')  
        print(f"找到 {len(scripts)} 个脚本标签")  
        
        # 查找包含JSON的脚本  
        json_scripts = []  
        for i, script in enumerate(scripts):  
            if script.string and len(script.string) > 100:  
                script_content = script.string.lower()  
                if any(keyword in script_content for keyword in ['json', 'submissions', 'notes', 'papers']):  
                    json_scripts.append((i, script.string))  
                    print(f"可能的JSON脚本 {i}: {script.string[:200]}...")  
        
        print(f"找到 {len(json_scripts)} 个可能包含数据的脚本")  
        
        # 查找所有链接  
        links = soup.find_all('a', href=True)  
        all_links = [link['href'] for link in links]  
        pdf_links = [link for link in all_links if 'pdf?id=' in link]  
        
        print(f"所有链接数量: {len(all_links)}")  
        print(f"PDF链接数量: {len(pdf_links)}")  
        
        if pdf_links:  
            print("找到的PDF链接示例:")  
            for link in pdf_links[:5]:  # 只显示前5个  
                print(f"  {link}")  
        
        # 查找其他可能的论文相关链接  
        paper_links = [link for link in all_links if any(keyword in link for keyword in ['forum?id=', 'forum/', 'pdf/', 'paper'])]  
        print(f"论文相关链接数量: {len(paper_links)}")  
        
        if paper_links:  
            print("论文相关链接示例:")  
            for link in paper_links[:5]:  
                print(f"  {link}")  
        
        return pdf_links  
        
    except Exception as e:  
        print(f"调试失败: {str(e)}")  
        return []  

if __name__ == "__main__":  
    # 测试不同的URL格式  
    urls_to_test = [  
        "https://openreview.net/group?id=ICLR.cc/2025/Conference#tab-accept-oral",  
        "https://openreview.net/group?id=ICLR.cc/2025/Conference",  
        "https://openreview.net/group?id=ICLR.cc/2025/Conference&tab=accept-oral"  
    ]  
    
    for url in urls_to_test:  
        print(f"\n{'='*60}")  
        print(f"测试URL: {url}")  
        print('='*60)  
        result = debug_fetch_paper(url)  
        print(f"结果: 找到 {len(result)} 个PDF链接")