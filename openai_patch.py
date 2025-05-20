# openai_patch.py  
import os  
import sys  

# 只设置HTTP/HTTPS代理，不设置SOCKS代理  
os.environ['http_proxy'] = 'http://172.28.16.1:7890'  
os.environ['https_proxy'] = 'http://172.28.16.1:7890'  
# 确保没有设置ALL_PROXY  
if 'ALL_PROXY' in os.environ:  
    del os.environ['ALL_PROXY']  

# 导入原始脚本  
import final